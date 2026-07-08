"""Tests for ``BeforeSummarizationHook`` registration and dispatch.

Verifies the runtime-checkable Protocol gating, dispatch ordering,
per-hook error isolation, and idempotent (un)registration.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from langchain_core.messages import HumanMessage

import app.core.chat.memory.summarization_hook as _mod
from app.core.chat.memory.summarization_hook import (
    BeforeSummarizationHook,
    SummarizationEvent,
    dispatch_summarization_hooks,
    register_summarization_hook,
    unregister_summarization_hook,
)


@pytest.fixture(autouse=True)
def _clear_hooks() -> Any:
    """Wipe the module-level hook registry before and after every test."""
    _mod._summarization_hooks.clear()
    yield
    _mod._summarization_hooks.clear()


def _make_event(thread_id: str = "t-1") -> SummarizationEvent:
    return SummarizationEvent(
        thread_id=thread_id,
        user_id=uuid4(),
        message_count=3,
        messages=(HumanMessage(content="a"), HumanMessage(content="b")),
    )


def test_register_rejects_non_callable() -> None:
    with pytest.raises(TypeError, match="BeforeSummarizationHook"):
        register_summarization_hook("not-callable")  # type: ignore[arg-type]


def test_register_then_dispatch_invokes_hook() -> None:
    seen: list[SummarizationEvent] = []

    def hook(event: SummarizationEvent) -> None:
        seen.append(event)

    register_summarization_hook(hook)
    event = _make_event()
    dispatch_summarization_hooks(event)
    assert seen == [event]


def test_unregister_removes_hook() -> None:
    seen: list[SummarizationEvent] = []

    def hook(event: SummarizationEvent) -> None:
        seen.append(event)

    register_summarization_hook(hook)
    unregister_summarization_hook(hook)
    dispatch_summarization_hooks(_make_event())
    assert seen == []


def test_register_is_idempotent() -> None:
    def hook(event: SummarizationEvent) -> None:
        pass

    register_summarization_hook(hook)
    register_summarization_hook(hook)

    assert len(_mod._summarization_hooks) == 1


def test_unregister_unknown_hook_is_noop() -> None:
    def hook(event: SummarizationEvent) -> None:
        pass

    # Should not raise even though the hook was never registered.
    unregister_summarization_hook(hook)


def test_dispatch_isolates_hook_errors(caplog: pytest.LogCaptureFixture) -> None:
    succeeded: list[str] = []

    def good(event: SummarizationEvent) -> None:
        succeeded.append("good")

    def bad(event: SummarizationEvent) -> None:
        raise RuntimeError("boom")

    register_summarization_hook(bad)
    register_summarization_hook(good)
    dispatch_summarization_hooks(_make_event())
    # The good hook must still fire even if an earlier one raised.
    assert succeeded == ["good"]


def test_summarization_event_is_frozen() -> None:
    event = _make_event()
    with pytest.raises((AttributeError, Exception)):
        event.thread_id = "mutated"  # type: ignore[misc]


def test_summarization_event_messages_is_tuple() -> None:
    event = _make_event()
    assert isinstance(event.messages, tuple)
    assert len(event.messages) == 2


def test_before_summarization_hook_is_runtime_checkable() -> None:
    def hook(event: SummarizationEvent) -> None:
        pass

    assert isinstance(hook, BeforeSummarizationHook)
