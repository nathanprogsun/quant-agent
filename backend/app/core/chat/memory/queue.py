"""Per-thread debounced MemoryUpdateQueue (P4.5).

Ports deer-flow's ``agents/memory/queue.py`` contract. Debounces flush
triggers per thread for ``update_debounce_seconds`` (default 30s) and drains
on a ``ThreadPoolExecutor(max_workers=4)``. Each drain runs the
MemoryUpdater inside a fresh asyncio loop (the queue is invoked from sync
middleware hook sites) and persists via the injected session factory.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Protocol

from app.config.memory_config import MemoryConfig

logger = logging.getLogger(__name__)


class UpdaterProtocol(Protocol):
    async def update_from_conversation(
        self, messages: Any, *, existing_facts: Any = ...
    ) -> Any: ...

    async def apply(self, user_id: Any, result: Any, session_factory: Any) -> None: ...


class MemoryUpdateQueue:
    """Debounced, thread-pool-backed memory update queue.

    Args:
        updater: MemoryUpdater (or fake) exposing update_from_conversation + apply.
        config: MemoryConfig (debounce window).
        session_factory: Async session factory used by apply(). Optional at
            construction; can be set later via set_session_factory for tests.
        max_workers: Worker count for the drain pool (default 4 per spec).
    """

    def __init__(
        self,
        *,
        updater: UpdaterProtocol,
        config: MemoryConfig,
        session_factory: Any | None = None,
        max_workers: int = 4,
    ) -> None:
        self._updater = updater
        self._config = config
        self._session_factory = session_factory
        self.max_workers = max_workers
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="memory-update"
        )
        self._timers: dict[str, threading.Timer] = {}
        self._pending: dict[str, tuple[Any, list[Any]]] = {}
        self._lock = threading.Lock()

    def set_session_factory(self, session_factory: Any) -> None:
        self._session_factory = session_factory

    def enqueue(self, thread_id: str, user_id: Any, messages: list[Any]) -> None:
        """Schedule (or re-schedule) a debounced flush for ``thread_id``."""
        with self._lock:
            previous = self._timers.pop(thread_id, None)
            if previous is not None:
                previous.cancel()
            self._pending[thread_id] = (user_id, list(messages))
            timer = threading.Timer(
                self._config.update_debounce_seconds,
                self._drain,
                args=(thread_id,),
            )
            timer.daemon = True
            self._timers[thread_id] = timer
        timer.start()

    def flush(self) -> None:
        """Cancel all pending timers and drain every thread immediately."""
        timers: list[threading.Timer] = []
        pending: list[tuple[str, Any, list[Any]]] = []
        with self._lock:
            timers = list(self._timers.values())
            self._timers.clear()
            for thread_id, (user_id, messages) in self._pending.items():
                pending.append((thread_id, user_id, messages))
            self._pending.clear()
        for timer in timers:
            timer.cancel()
        for thread_id, user_id, messages in pending:
            self._executor.submit(self._run, thread_id, user_id, messages, self._session_factory)

    def _drain(self, thread_id: str) -> None:
        with self._lock:
            self._timers.pop(thread_id, None)
            entry = self._pending.pop(thread_id, None)
        if entry is None:
            return
        user_id, messages = entry
        self._executor.submit(self._run, thread_id, user_id, messages, self._session_factory)

    def _run(
        self,
        thread_id: str,
        user_id: Any,
        messages: list[Any],
        session_factory: Any,
    ) -> None:
        """Drain worker: run the updater in a fresh event loop and persist.

        Uses an explicit ``new_event_loop`` + ``run_until_complete`` rather than
        ``asyncio.run`` so the calling thread's current-event-loop state is not
        disturbed (older call sites rely on ``asyncio.get_event_loop()``).
        """
        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(self._updater.update_from_conversation(messages))
            if session_factory is not None:
                loop.run_until_complete(self._updater.apply(user_id, result, session_factory))
        except Exception:
            logger.exception("Memory update failed for thread %s", thread_id)
        finally:
            loop.close()

    def shutdown(self, *, wait: bool = True) -> None:
        """Cancel timers and shut down the executor."""
        with self._lock:
            timers = list(self._timers.values())
            self._timers.clear()
            self._pending.clear()
        for timer in timers:
            timer.cancel()
        self._executor.shutdown(wait=wait, cancel_futures=True)


# ---- Module-level singleton wiring (set during app lifespan) ----

_global_queue: MemoryUpdateQueue | None = None


def set_memory_update_queue(queue: MemoryUpdateQueue | None) -> None:
    """Set the process-wide MemoryUpdateQueue (called from lifespan)."""
    global _global_queue
    _global_queue = queue


def get_memory_update_queue() -> MemoryUpdateQueue | None:
    return _global_queue


__all__ = [
    "MemoryUpdateQueue",
    "UpdaterProtocol",
    "get_memory_update_queue",
    "set_memory_update_queue",
]
