"""Summarization → memory queue bridge (P4.5).

Bridges ``SummarizationMiddleware`` events to the ``MemoryUpdateQueue``. The
middleware produces a ``SummarizationEvent`` when a conversation crosses the
summarization threshold; ``memory_flush_hook`` enqueues a debounced update.

The hook protocol is exposed as :class:`BeforeSummarizationHook` (a runtime
checkable Protocol) so external subsystems can subscribe to summarization
events without coupling to the in-process flush hook.
"""

from __future__ import annotations

import contextlib
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from langchain_core.messages import BaseMessage

__all__ = [
    "BeforeSummarizationHook",
    "FlushHook",
    "SummarizationEvent",
    "dispatch_summarization_hooks",
    "get_summarization_flush_hook",
    "memory_flush_hook",
    "register_summarization_hook",
    "set_summarization_flush_hook",
    "unregister_summarization_hook",
]

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class SummarizationEvent:
    """Event emitted when a conversation crosses the summarization threshold.

    The dataclass is frozen so subscribers cannot mutate the payload after
    the event has been dispatched. ``messages`` is held as a tuple to
    enforce immutability at the collection level too.
    """

    thread_id: str
    user_id: Any
    message_count: int
    messages: tuple[BaseMessage, ...] = ()


@runtime_checkable
class BeforeSummarizationHook(Protocol):
    """Protocol for hooks invoked before summarization runs.

    Implementations can use this to capture the pre-summarization state
    (e.g. emit telemetry, snapshot checkpoints, or write to an external
    store). Use :func:`register_summarization_hook` to subscribe.
    """

    def __call__(self, event: SummarizationEvent) -> None: ...


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

# External subscribers invoked alongside the in-process flush hook. Use
# register_summarization_hook / unregister_summarization_hook so callers
# do not need to import this module's private globals.
_summarization_hooks: list[BeforeSummarizationHook] = []


def set_summarization_flush_hook(hook: FlushHook | None) -> None:
    global _flush_hook
    _flush_hook = hook


def get_summarization_flush_hook() -> FlushHook | None:
    return _flush_hook


def register_summarization_hook(hook: BeforeSummarizationHook) -> None:
    """Subscribe a callable to summarization events.

    No-op when the same hook instance is already registered; runtime-checkable
    Protocol membership is verified so callers get a clear error early.
    """
    if not isinstance(hook, BeforeSummarizationHook):
        raise TypeError(f"{hook!r} does not satisfy BeforeSummarizationHook protocol")
    if hook in _summarization_hooks:
        return
    _summarization_hooks.append(hook)


def unregister_summarization_hook(hook: BeforeSummarizationHook) -> None:
    """Remove a previously-registered hook (no-op when not present)."""
    with contextlib.suppress(ValueError):
        _summarization_hooks.remove(hook)


def dispatch_summarization_hooks(event: SummarizationEvent) -> None:
    """Invoke every registered hook with ``event``, swallowing per-hook errors."""
    for hook in list(_summarization_hooks):
        try:
            hook(event)
        except Exception:
            hook_name = getattr(hook, "__name__", None) or type(hook).__name__
            logger.exception("BeforeSummarizationHook %s failed", hook_name)
