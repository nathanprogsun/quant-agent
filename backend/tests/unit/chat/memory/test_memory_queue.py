"""Tests for MemoryUpdateQueue — per-thread debounce (P4.5)."""

from __future__ import annotations

import time
from typing import Any

from app.config.memory_config import MemoryConfig
from app.core.chat.memory.queue import MemoryUpdateQueue


class _RecordingUpdater:
    """Fake updater that records enqueue/apply calls."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, Any, Any]] = []
        self.apply_calls: list[tuple[str, Any, Any]] = []

    async def update_from_conversation(self, messages: Any, *, existing_facts: Any = None) -> Any:
        self.calls.append(("update", messages, existing_facts))
        return None

    async def apply(self, user_id: Any, result: Any, session_factory: Any) -> None:
        self.apply_calls.append((user_id, result, session_factory))


def test_queue_has_thread_pool_with_max_workers_four() -> None:
    queue = MemoryUpdateQueue(updater=_RecordingUpdater(), config=MemoryConfig())
    assert queue.max_workers == 4
    assert queue._executor._max_workers == 4
    queue.shutdown(wait=False)


def test_enqueue_debounces_per_thread() -> None:
    updater = _RecordingUpdater()
    queue = MemoryUpdateQueue(updater=updater, config=MemoryConfig(update_debounce_seconds=0.05))
    try:
        # Enqueue twice for the same thread rapidly; only one drain should fire.
        queue.enqueue("t1", "u1", ["m1"])
        queue.enqueue("t1", "u1", ["m1", "m2"])
        # Wait past debounce.
        time.sleep(0.2)
    finally:
        queue.shutdown(wait=True)
    # The pending state was overwritten; only one drain job submitted.
    assert len(updater.calls) == 1
    assert updater.calls[0][1] == ["m1", "m2"]


def test_enqueue_separate_threads_drain_independently() -> None:
    updater = _RecordingUpdater()
    queue = MemoryUpdateQueue(updater=updater, config=MemoryConfig(update_debounce_seconds=0.02))
    try:
        queue.enqueue("t1", "u1", ["a"])
        queue.enqueue("t2", "u2", ["b"])
        time.sleep(0.2)
    finally:
        queue.shutdown(wait=True)
    assert len(updater.calls) == 2


def test_flush_drains_immediately() -> None:
    updater = _RecordingUpdater()
    queue = MemoryUpdateQueue(updater=updater, config=MemoryConfig(update_debounce_seconds=30.0))
    try:
        queue.enqueue("t1", "u1", ["m"])
        queue.flush()  # must not wait 30s
    finally:
        queue.shutdown(wait=True)
    assert len(updater.calls) == 1


def test_run_uses_async_loop_and_session_factory() -> None:
    updater = _RecordingUpdater()
    queue = MemoryUpdateQueue(updater=updater, config=MemoryConfig(update_debounce_seconds=0.0))
    factory = object()  # sentinel; fake updater records it
    try:
        queue._run("t1", "u1", ["m"], session_factory=factory)
    finally:
        queue.shutdown(wait=True)
    assert len(updater.apply_calls) == 1
    assert updater.apply_calls[0][0] == "u1"
    assert updater.apply_calls[0][2] is factory
