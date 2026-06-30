"""Production wiring for the memory evolution subsystem (P4.4/P4.5).

Builds the ``MemoryUpdateQueue`` (with a ChatOpenAI-backed LLM adapter and the
``MemoryUpdater``) and installs the process-wide singletons:

- ``set_memory_update_queue`` — consumed by ``MemoryMiddleware.after_model``.
- ``set_summarization_flush_hook`` — consumed by ``SummarizationMiddleware``.

Both entry points debounce into the same per-thread queue, so duplicate
triggers within 30s collapse.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.chat.memory.llm_adapter import MemoryLLMAdapter
from app.core.chat.memory.queue import (
    MemoryUpdateQueue,
    get_memory_update_queue,
    set_memory_update_queue,
)
from app.core.chat.memory.summarization_hook import (
    SummarizationEvent,
    memory_flush_hook,
    set_summarization_flush_hook,
)
from app.core.chat.memory.updater import MemoryUpdater

if TYPE_CHECKING:
    from app.settings import Settings


def build_memory_update_queue(settings: Settings, session_factory: object) -> MemoryUpdateQueue:
    """Construct a fully-wired MemoryUpdateQueue (does not install it)."""
    llm = MemoryLLMAdapter(settings)
    updater = MemoryUpdater(llm=llm, config=settings.memory)
    return MemoryUpdateQueue(
        updater=updater,
        config=settings.memory,
        session_factory=session_factory,
    )


def install_memory_subsystem(settings: Settings, session_factory: object) -> MemoryUpdateQueue:
    """Build, install, and return the process-wide MemoryUpdateQueue.

    Also installs the summarization flush hook bridging SummarizationMiddleware
    events into the queue via ``memory_flush_hook``.
    """
    queue = build_memory_update_queue(settings, session_factory)
    set_memory_update_queue(queue)

    def _flush(event: SummarizationEvent) -> None:
        active = get_memory_update_queue()
        if active is not None:
            memory_flush_hook(event, active)

    set_summarization_flush_hook(_flush)
    return queue


def shutdown_memory_subsystem(queue: MemoryUpdateQueue | None) -> None:
    """Tear down the process-wide memory queue and hook."""
    set_summarization_flush_hook(None)
    set_memory_update_queue(None)
    if queue is not None:
        queue.shutdown(wait=False)


__all__ = [
    "build_memory_update_queue",
    "install_memory_subsystem",
    "shutdown_memory_subsystem",
]
