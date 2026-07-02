"""Tests for ``make_sync_tool_wrapper`` (sync path for async tools)."""

from __future__ import annotations

import threading

import pytest

from app.tools.sync_tool_wrapper import make_sync_tool_wrapper


def _run_sync(callable_obj):
    """Run a sync callable in a fresh thread so ``asyncio.run`` works inside the wrapper."""

    holder: dict = {}

    def _runner() -> None:
        try:
            holder["v"] = callable_obj()
        except Exception as exc:  # pragma: no cover - re-raised below
            holder["err"] = exc

    t = threading.Thread(target=_runner)
    t.start()
    t.join(timeout=5)
    if "err" in holder:
        raise holder["err"]  # type: ignore[misc]
    return holder.get("v")


def test_wrapper_runs_async_coroutine_when_called_from_no_loop() -> None:
    async def coro(x: int) -> int:
        return x * 2

    wrapped = make_sync_tool_wrapper(coro, "test")
    assert _run_sync(lambda: wrapped(21)) == 42


def test_wrapper_propagates_exception() -> None:
    async def coro() -> None:
        raise ValueError("boom")

    wrapped = make_sync_tool_wrapper(coro, "explodes")

    def _call() -> None:
        wrapped()

    try:
        _run_sync(_call)
    except ValueError as exc:
        assert str(exc) == "boom"
    else:
        pytest.fail("expected ValueError")


def test_wrapper_runs_coroutine_returning_none() -> None:
    async def coro() -> None:
        return None

    wrapped = make_sync_tool_wrapper(coro, "none-tool")
    assert _run_sync(wrapped) is None
