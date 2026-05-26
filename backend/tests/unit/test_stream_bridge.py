"""Unit tests for MemoryStreamBridge."""

from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest

from app.common.stream_bridge.base import END_SENTINEL, HEARTBEAT_SENTINEL
from app.common.stream_bridge.memory import MemoryStreamBridge


@pytest.fixture
def bridge() -> MemoryStreamBridge:
    return MemoryStreamBridge(queue_maxsize=8)


async def test_publish_and_subscribe(bridge: MemoryStreamBridge) -> None:
    """Basic pub/sub flow."""
    run_id = uuid4()

    async def producer() -> None:
        await bridge.publish(run_id, "messages", {"text": "hello"})
        await bridge.publish(run_id, "messages", {"text": "world"})
        await bridge.publish_end(run_id)

    task = asyncio.create_task(producer())
    events = []
    async for evt in bridge.subscribe(run_id, heartbeat_interval=1.0):
        events.append(evt)

    assert len(events) == 3  # 2 messages + END
    assert events[0].data == {"text": "hello"}
    assert events[1].data == {"text": "world"}
    assert events[2] is END_SENTINEL
    await task


async def test_heartbeat(bridge: MemoryStreamBridge) -> None:
    """Heartbeat fires when no events arrive within interval."""
    run_id = uuid4()

    events = []
    async for evt in bridge.subscribe(run_id, heartbeat_interval=0.1):
        events.append(evt)
        if len(events) >= 3:
            break

    assert all(evt is HEARTBEAT_SENTINEL for evt in events)


async def test_reconnection(bridge: MemoryStreamBridge) -> None:
    """Reconnect via Last-Event-ID replays missed events."""
    run_id = uuid4()

    await bridge.publish(run_id, "messages", {"idx": 0})
    await bridge.publish(run_id, "messages", {"idx": 1})
    await bridge.publish(run_id, "messages", {"idx": 2})
    await bridge.publish_end(run_id)

    # Reconnect from event index 1's id
    first_events = []
    async for evt in bridge.subscribe(run_id, heartbeat_interval=1.0):
        first_events.append(evt)
        if len(first_events) >= 2:
            break

    reconnect_id = first_events[0].id  # first event id

    replayed = []
    async for evt in bridge.subscribe(run_id, last_event_id=reconnect_id, heartbeat_interval=1.0):
        replayed.append(evt)

    # Should get events after reconnect_id + END
    assert replayed[0].data == {"idx": 1}
    assert replayed[1].data == {"idx": 2}
    assert replayed[-1] is END_SENTINEL


async def test_ring_eviction(bridge: MemoryStreamBridge) -> None:
    """Buffer evicts oldest events when exceeding maxsize."""
    run_id = uuid4()

    for i in range(12):
        await bridge.publish(run_id, "messages", {"idx": i})

    events = []
    async for evt in bridge.subscribe(run_id, heartbeat_interval=1.0):
        events.append(evt)
        if len(events) >= 12:
            break

    # Buffer maxsize=8, so oldest 4 events evicted
    data_events = [e for e in events if e is not END_SENTINEL]
    assert data_events[0].data["idx"] == 4  # first surviving event


async def test_publish_end(bridge: MemoryStreamBridge) -> None:
    """publish_end signals stream termination."""
    run_id = uuid4()

    await bridge.publish_end(run_id)

    events = []
    async for evt in bridge.subscribe(run_id, heartbeat_interval=1.0):
        events.append(evt)

    assert events[-1] is END_SENTINEL


async def test_cleanup(bridge: MemoryStreamBridge) -> None:
    """cleanup removes stream state after delay."""
    run_id = uuid4()

    await bridge.publish(run_id, "messages", {"data": 1})
    assert run_id in bridge._streams

    await bridge.cleanup(run_id, delay=0)
    assert run_id not in bridge._streams
