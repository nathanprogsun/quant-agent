"""Tests for MemoryMiddleware write-back hook (P4.4).

MemoryMiddleware performs NO message injection (that is DynamicContextMiddleware's
job, P4.2). Its after_model dispatches a flush trigger to the MemoryUpdateQueue
when len(messages) >= max_messages.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from langchain_core.messages import HumanMessage

from app.config.memory_config import MemoryConfig
from app.core.chat.memory.queue import (
    MemoryUpdateQueue,
    set_memory_update_queue,
)
from app.core.chat.memory.updater import MemoryUpdateResult
from app.core.chat.middlewares.memory_middleware import MemoryMiddleware


class _RecordingUpdater:
    def __init__(self) -> None:
        self.calls: list[Any] = []

    async def update_from_conversation(
        self, messages: Any, *, existing_facts: Any = None
    ) -> MemoryUpdateResult:
        self.calls.append(messages)
        return MemoryUpdateResult(user="u")

    async def apply(self, user_id: Any, result: Any, session_factory: Any) -> None:
        self.calls.append(("apply", user_id, result, session_factory))


@pytest.fixture
def recording_queue() -> MemoryUpdateQueue:
    queue = MemoryUpdateQueue(
        updater=_RecordingUpdater(),
        config=MemoryConfig(update_debounce_seconds=30.0),
    )
    set_memory_update_queue(queue)
    yield queue
    set_memory_update_queue(None)
    queue.shutdown(wait=False)


@pytest.mark.asyncio
async def test_after_model_fires_when_threshold_met(
    recording_queue: MemoryUpdateQueue,
) -> None:
    mw = MemoryMiddleware(max_messages=3)
    messages = [HumanMessage(content=str(i)) for i in range(3)]
    state = {"messages": messages}
    config = {"configurable": {"user_id": uuid4(), "thread_id": "t1"}}

    await mw.before_model(state, config)
    result = await mw.after_model(state, config)

    assert result is None  # no state patch, no message mutation
    # Flush immediately so the drain runs synchronously.
    recording_queue.flush(wait=True)
    # The updater was invoked with the conversation messages.
    assert len(recording_queue._updater.calls) == 1


@pytest.mark.asyncio
async def test_after_model_no_fire_under_threshold(
    recording_queue: MemoryUpdateQueue,
) -> None:
    mw = MemoryMiddleware(max_messages=50)
    messages = [HumanMessage(content="hi")]
    state = {"messages": messages}
    config = {"configurable": {"user_id": uuid4(), "thread_id": "t1"}}

    await mw.after_model(state, config)
    recording_queue.flush()
    assert len(recording_queue._updater.calls) == 0


@pytest.mark.asyncio
async def test_after_model_does_not_mutate_messages(
    recording_queue: MemoryUpdateQueue,
) -> None:
    mw = MemoryMiddleware(max_messages=2)
    messages = [HumanMessage(content="a"), HumanMessage(content="b")]
    original_ids = [m.id for m in messages]
    state = {"messages": messages}
    config = {"configurable": {"user_id": uuid4(), "thread_id": "t1"}}

    await mw.before_model(state, config)
    await mw.after_model(state, config)

    assert [m.id for m in messages] == original_ids
    assert len(messages) == 2


@pytest.mark.asyncio
async def test_before_model_is_noop(recording_queue: MemoryUpdateQueue) -> None:
    mw = MemoryMiddleware(max_messages=3)
    state = {"messages": [HumanMessage(content="hi")]}
    out = await mw.before_model(state, {"configurable": {"user_id": uuid4()}})
    assert out is None
