"""Tests for the summarization hook bridge (P4.5)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from langchain_core.messages import HumanMessage
from langgraph.runtime import Runtime

from app.core.chat.memory.summarization_hook import (
    SummarizationEvent,
    memory_flush_hook,
    set_summarization_flush_hook,
)
from app.core.chat.middlewares.summarization_middleware import SummarizationMiddleware


class _RecordingQueue:
    def __init__(self) -> None:
        self.enqueued: list[tuple[str, Any, Any]] = []

    def enqueue(self, thread_id: str, user_id: Any, messages: Any) -> None:
        self.enqueued.append((thread_id, user_id, messages))


@pytest.mark.asyncio
async def test_memory_flush_hook_enqueues_when_user_id_present() -> None:
    queue = _RecordingQueue()
    event = SummarizationEvent(
        thread_id="t1",
        user_id="u1",
        message_count=50,
        messages=[HumanMessage(content="hi")],
    )
    memory_flush_hook(event, queue)
    assert queue.enqueued == [("t1", "u1", event.messages)]


def test_memory_flush_hook_skips_when_user_id_missing() -> None:
    queue = _RecordingQueue()
    event = SummarizationEvent(thread_id="t1", user_id=None, message_count=50, messages=[])
    memory_flush_hook(event, queue)
    assert queue.enqueued == []


@pytest.mark.asyncio
async def test_summarization_middleware_dispatches_hook_on_threshold() -> None:
    queue = _RecordingQueue()
    set_summarization_flush_hook(lambda event: memory_flush_hook(event, queue))
    try:
        mw = SummarizationMiddleware(max_messages=5, enabled=True)
        messages = [HumanMessage(content=str(i)) for i in range(6)]
        await mw.before_model({"messages": messages}, {})
        await mw.after_model(
            {"messages": messages}, Runtime(context=SimpleNamespace(thread_id="test", user_id="u1"))
        )
    finally:
        set_summarization_flush_hook(None)
    assert len(queue.enqueued) == 1
    assert queue.enqueued[0][1] == "u1"


@pytest.mark.asyncio
async def test_summarization_middleware_no_dispatch_under_threshold() -> None:
    queue = _RecordingQueue()
    set_summarization_flush_hook(lambda event: memory_flush_hook(event, queue))
    try:
        mw = SummarizationMiddleware(max_messages=50, enabled=True)
        messages = [HumanMessage(content="hi")]
        await mw.before_model({"messages": messages}, {})
        await mw.after_model(
            {"messages": messages}, Runtime(context=SimpleNamespace(thread_id="test", user_id="u1"))
        )
    finally:
        set_summarization_flush_hook(None)
    assert queue.enqueued == []
