"""Summarization → memory queue bridge (P4.5).

Bridges ``SummarizationMiddleware`` events to the ``MemoryUpdateQueue``. The
middleware produces a ``SummarizationEvent`` when a conversation crosses the
summarization threshold; ``memory_flush_hook`` enqueues a debounced update.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from langchain_core.messages import BaseMessage

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SummarizationEvent:
    """Event emitted when a conversation crosses the summarization threshold."""

    thread_id: str
    user_id: Any
    message_count: int
    messages: list[BaseMessage] = field(default_factory=list)


class _QueueLike(Protocol):
    def enqueue(self, thread_id: str, user_id: Any, messages: list[Any]) -> None: ...


def memory_flush_hook(event: SummarizationEvent, queue: _QueueLike) -> None:
    """Enqueue a debounced memory update for the event's thread.

    Skips when ``user_id`` is missing (no per-user memory to evolve).
    """
    if event.user_id is None:
        logger.debug("Summarization event for thread %s had no user_id; skipping", event.thread_id)
        return
    queue.enqueue(event.thread_id, event.user_id, list(event.messages))


# Hook installed by SummarizationMiddleware to dispatch events. Set via
# set_summarization_flush_hook from lifespan/conftest.
FlushHook = Callable[[SummarizationEvent], None]
_flush_hook: FlushHook | None = None


def set_summarization_flush_hook(hook: FlushHook | None) -> None:
    global _flush_hook
    _flush_hook = hook


def get_summarization_flush_hook() -> FlushHook | None:
    return _flush_hook


__all__ = [
    "FlushHook",
    "SummarizationEvent",
    "get_summarization_flush_hook",
    "memory_flush_hook",
    "set_summarization_flush_hook",
]
