"""Tests for the persistent isolated subagent event loop.

Ports deer-flow's subagent-persistent-loop scaffolding. The loop must:
- be lazily created on first call
- run in a daemon thread named "subagent-persistent-loop"
- propagate ContextVar via contextvars.copy_context() when submitted from
  outside the loop (via asyncio.run_coroutine_threadsafe)
- shut down via atexit within 1 second of process exit
"""

from __future__ import annotations

import asyncio
import contextvars
import time

import pytest

import app.core.chat.subagents.executor as executor_module
from app.core.chat.subagents.executor import (
    _get_isolated_subagent_loop,
    _shutdown_isolated_subagent_loop,
    _submit_to_isolated_loop_in_context,
)


@pytest.fixture(autouse=True)
def _reset_loop() -> None:
    """Ensure a clean isolated loop for every test."""
    _shutdown_isolated_subagent_loop()
    yield
    _shutdown_isolated_subagent_loop()


def test_get_isolated_subagent_loop_returns_same_loop_on_second_call() -> None:
    loop1 = _get_isolated_subagent_loop()
    loop2 = _get_isolated_subagent_loop()
    assert loop1 is loop2
    assert loop1.is_running()


def test_daemon_thread_named_subagent_persistent_loop_is_alive() -> None:
    loop = _get_isolated_subagent_loop()
    # The daemon thread that hosts the loop must be alive while the loop runs
    thread = executor_module._isolated_subagent_loop_thread
    assert thread is not None
    assert thread.is_alive()
    assert thread.daemon is True
    assert thread.name == "subagent-persistent-loop"
    assert loop.is_running()


def test_shutdown_stops_loop_and_joins_thread_within_timeout() -> None:
    _get_isolated_subagent_loop()
    thread = executor_module._isolated_subagent_loop_thread
    assert thread is not None and thread.is_alive()

    start = time.monotonic()
    _shutdown_isolated_subagent_loop()
    elapsed = time.monotonic() - start
    assert elapsed < 1.0, f"shutdown took {elapsed:.3f}s; expected <1s"
    assert not thread.is_alive()


@pytest.mark.asyncio
async def test_submission_propagates_contextvar_via_copy_context() -> None:
    captured: dict[str, str] = {}

    sentinel = contextvars.ContextVar("sentinel_token", default="missing")

    async def coro() -> str:
        captured["value"] = sentinel.get()
        return captured["value"]

    token = sentinel.set("expected-subagent-context")
    try:
        parent_ctx = contextvars.copy_context()
        future = _submit_to_isolated_loop_in_context(parent_ctx, lambda: coro())
        result = await asyncio.wrap_future(future)
    finally:
        sentinel.reset(token)

    assert result == "expected-subagent-context"
    assert captured["value"] == "expected-subagent-context"
