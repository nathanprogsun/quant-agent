"""Tests for SubagentLimitMiddleware wired to the real subagent cache."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from langgraph.runtime import Runtime

import app.core.chat.tools.builtin.task_tool as task_tool_module
from app.core.chat.middlewares.subagent_limit_middleware import (
    MAX_CONCURRENT_SUBAGENTS,
    MAX_SUBAGENT_LIMIT,
    MIN_SUBAGENT_LIMIT,
    SubagentLimitMiddleware,
    _clamp_subagent_limit,
)


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    task_tool_module._subagent_usage_cache.clear()
    yield
    task_tool_module._subagent_usage_cache.clear()


def test_constants_have_expected_values() -> None:
    assert MIN_SUBAGENT_LIMIT == 2
    assert MAX_SUBAGENT_LIMIT == 4
    assert MAX_CONCURRENT_SUBAGENTS == 3


@pytest.mark.parametrize(
    "raw,clamped",
    [
        (0, MIN_SUBAGENT_LIMIT),
        (1, MIN_SUBAGENT_LIMIT),
        (2, 2),
        (3, 3),
        (4, 4),
        (5, MAX_SUBAGENT_LIMIT),
        (100, MAX_SUBAGENT_LIMIT),
    ],
)
def test_clamp_subagent_limit(raw: int, clamped: int) -> None:
    assert _clamp_subagent_limit(raw) == clamped


def test_clamps_max_concurrent_in_constructor() -> None:
    mw = SubagentLimitMiddleware(max_concurrent=99)
    assert mw._max_concurrent == MAX_SUBAGENT_LIMIT
    mw = SubagentLimitMiddleware(max_concurrent=1)
    assert mw._max_concurrent == MIN_SUBAGENT_LIMIT


@pytest.fixture
def main_event_loop() -> Any:
    """Per-test MainThread event loop.

    ``asyncio.run()`` deletes the loop on exit which breaks unrelated sync
    tests that use ``asyncio.get_event_loop().run_until_complete(...)``.
    Set the loop explicitly to keep it thread-local across the test,
    restoring the previous loop on teardown.
    """
    prior: asyncio.AbstractEventLoop | None
    try:
        prior = asyncio.get_event_loop()
    except RuntimeError:
        prior = None
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        yield loop
    finally:
        loop.close()
        if prior is not None:
            asyncio.set_event_loop(prior)
        else:
            asyncio.set_event_loop(None)


def test_before_model_allows_under_limit(main_event_loop: Any) -> None:
    """Under the limit, before_model returns nothing — call proceeds."""
    task_tool_module._subagent_usage_cache["call-1"] = {
        "input_tokens": 1,
        "output_tokens": 1,
        "total_tokens": 2,
    }
    task_tool_module._subagent_usage_cache["call-2"] = {
        "input_tokens": 1,
        "output_tokens": 1,
        "total_tokens": 2,
    }
    mw = SubagentLimitMiddleware(max_concurrent=3)
    out = main_event_loop.run_until_complete(mw.before_model({"messages": []}, Runtime()))
    assert out is None


@pytest.mark.asyncio
async def test_before_model_blocks_when_cache_at_limit() -> None:
    """At the limit, before_model reports the limit so the call site can react."""
    for i in range(3):
        task_tool_module._subagent_usage_cache[f"call-{i}"] = {
            "input_tokens": 1,
            "output_tokens": 1,
            "total_tokens": 2,
        }
    mw = SubagentLimitMiddleware(max_concurrent=3)
    out = await mw.before_model({"messages": []}, Runtime())
    assert out is not None
    assert out.get("subagent_limit_reached") is True
    assert out.get("max_concurrent") == 3


@pytest.mark.asyncio
async def test_before_model_allows_just_under_limit() -> None:
    for i in range(2):
        task_tool_module._subagent_usage_cache[f"call-{i}"] = {
            "input_tokens": 1,
            "output_tokens": 1,
            "total_tokens": 2,
        }
    mw = SubagentLimitMiddleware(max_concurrent=3)
    out = await mw.before_model({"messages": []}, Runtime())
    assert out is None


def test_get_active_count_returns_zero_initially() -> None:
    mw = SubagentLimitMiddleware()
    assert mw.get_active_count() == 0


def test_get_limit_returns_max_concurrent() -> None:
    mw = SubagentLimitMiddleware(max_concurrent=2)
    assert mw.get_limit() == 2
