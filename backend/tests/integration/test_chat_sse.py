"""Integration tests for chat SSE streaming.

Tests: SSE output, reconnection via Last-Event-ID, heartbeat, concurrency control.
"""

from __future__ import annotations

from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest
from langchain_core.messages import HumanMessage

from app.common.runs.manager import ConflictError, RunManager
from app.common.runs.schemas import RunStatus
from app.common.stream_bridge.memory import MemoryStreamBridge
from app.web.api.chat.services import format_sse, normalize_input, sse_consumer

# ── Helpers ──────────────────────────────────────────────────


def _make_request(user_id: UUID | None = None) -> MagicMock:
    req = MagicMock()
    req.state = MagicMock()
    req.state.current_user_id = user_id or uuid4()
    req.headers = {}
    return req


# ── format_sse ───────────────────────────────────────────────


class TestFormatSse:
    def test_basic_event(self) -> None:
        result = format_sse("message", {"text": "hi"})
        assert "event: message\n" in result
        assert '"text": "hi"' in result

    def test_with_event_id(self) -> None:
        result = format_sse("chunk", "data", event_id="42")
        assert "id: 42\n" in result

    def test_none_data(self) -> None:
        result = format_sse("end", None)
        assert "data: null\n" in result


# ── normalize_input ──────────────────────────────────────────


class TestNormalizeInput:
    def test_empty_messages(self) -> None:
        result = normalize_input({"messages": []})
        assert result == {"messages": []}

    def test_valid_user_message(self) -> None:
        result = normalize_input(
            {"messages": [{"role": "user", "content": "hello"}]}
        )
        assert len(result["messages"]) == 1
        assert isinstance(result["messages"][0], HumanMessage)

    def test_invalid_role_raises_400(self) -> None:
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            normalize_input(
                {"messages": [{"role": "hacker", "content": "bad"}]}
            )
        assert exc_info.value.status_code == 400

    def test_oversized_message_raises_400(self) -> None:
        from fastapi import HTTPException

        big = "x" * 40000
        with pytest.raises(HTTPException) as exc_info:
            normalize_input(
                {"messages": [{"role": "user", "content": big}]}
            )
        assert exc_info.value.status_code == 400

    def test_unsupported_type_raises_400(self) -> None:
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            normalize_input({"messages": [123]})
        assert exc_info.value.status_code == 400


# ── SSE consumer ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_sse_consumer_streams_events() -> None:
    """SSE consumer yields formatted events then end."""
    bridge = MemoryStreamBridge()
    run_manager = RunManager()
    thread_id = uuid4()
    user_id = uuid4()

    record = await run_manager.create_or_reject(
        thread_id=thread_id,
        user_id=user_id,
    )

    await bridge.publish(record.run_id, "chunk", {"content": "Hi"})
    await bridge.publish_end(record.run_id)

    request = _make_request(user_id)

    frames = []
    async for frame in sse_consumer(bridge, record, request, run_manager):
        frames.append(frame)

    assert any("event: chunk" in f for f in frames)
    assert any("event: end" in f for f in frames)

    await bridge.close()


@pytest.mark.asyncio
async def test_sse_consumer_reconnection() -> None:
    """SSE consumer with Last-Event-ID replays from offset."""
    bridge = MemoryStreamBridge()
    run_manager = RunManager()
    thread_id = uuid4()
    user_id = uuid4()

    record = await run_manager.create_or_reject(
        thread_id=thread_id,
        user_id=user_id,
    )

    # Publish 3 events
    await bridge.publish(record.run_id, "chunk", {"n": 1})
    await bridge.publish(record.run_id, "chunk", {"n": 2})
    await bridge.publish(record.run_id, "chunk", {"n": 3})
    await bridge.publish_end(record.run_id)

    # First consumer gets all events
    request_full = _make_request(user_id)
    frames_full = []
    async for frame in sse_consumer(bridge, record, request_full, run_manager):
        frames_full.append(frame)

    # Extract the first event's id from the SSE frame (format: "id: <value>\n")
    first_event_id = None
    for line in frames_full[0].split("\n"):
        if line.startswith("id: "):
            first_event_id = line.split("id: ", 1)[1].strip()
            break

    # Second consumer reconnects using the real event id
    request_reconnect = _make_request(user_id)
    request_reconnect.headers = {"Last-Event-ID": first_event_id}
    frames_reconnect = []
    async for frame in sse_consumer(bridge, record, request_reconnect, run_manager):
        frames_reconnect.append(frame)

    # Reconnect should skip the first event
    assert len(frames_reconnect) < len(frames_full)

    await bridge.close()



@pytest.mark.asyncio
async def test_sse_consumer_heartbeat() -> None:
    """SSE consumer yields heartbeat on timeout."""
    bridge = MemoryStreamBridge()
    run_manager = RunManager()
    thread_id = uuid4()
    user_id = uuid4()

    record = await run_manager.create_or_reject(
        thread_id=thread_id,
        user_id=user_id,
    )

    # Don't publish anything — heartbeat should fire on timeout
    got_heartbeat = False
    async for event in bridge.subscribe(
        record.run_id, heartbeat_interval=0.1
    ):
        if event.event == "__heartbeat__":
            got_heartbeat = True
            break
        if event.event == "__end__":
            break

    assert got_heartbeat
    await bridge.close()


# ── Concurrency control ──────────────────────────────────────


@pytest.mark.asyncio
async def test_concurrent_reject_strategy() -> None:
    """Second run on same thread is rejected when strategy=reject."""
    run_manager = RunManager()
    thread_id = uuid4()
    user_id = uuid4()

    await run_manager.create_or_reject(
        thread_id=thread_id,
        user_id=user_id,
        multitask_strategy="reject",
    )

    with pytest.raises(ConflictError):
        await run_manager.create_or_reject(
            thread_id=thread_id,
            user_id=user_id,
            multitask_strategy="reject",
        )


@pytest.mark.asyncio
async def test_concurrent_interrupt_strategy() -> None:
    """Second run cancels the first when strategy=interrupt."""
    run_manager = RunManager()
    thread_id = uuid4()
    user_id = uuid4()

    r1 = await run_manager.create_or_reject(
        thread_id=thread_id,
        user_id=user_id,
        multitask_strategy="interrupt",
    )
    assert r1.status == RunStatus.PENDING

    r2 = await run_manager.create_or_reject(
        thread_id=thread_id,
        user_id=user_id,
        multitask_strategy="interrupt",
    )
    assert r2.run_id != r1.run_id

    r1_updated = await run_manager.get(r1.run_id)
    assert r1_updated.status == RunStatus.INTERRUPTED
