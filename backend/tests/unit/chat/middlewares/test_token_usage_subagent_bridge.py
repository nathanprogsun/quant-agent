"""Tests for the token_usage_middleware reverse-walk bridge (P3.4).

Ports deer-flow's token_usage_middleware.py:282-314 reverse-walk: when the
subagent completes, ``_subagent_usage_cache[tool_call_id]`` holds its token
usage; the middleware walks consecutive ``ToolMessage``s backward from the
new ``AIMessage``, looks up the dispatch ``AIMessage`` via ``_has_tool_call``
matching the tool_call_id, and merges the cached usage into the dispatch
message's ``usage_metadata``.
"""

from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.runtime import Runtime

import app.core.chat.tools.builtin.task_tool as task_tool_module
from app.core.chat.middlewares.token_usage_middleware import TokenUsageMiddleware


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    task_tool_module._subagent_usage_cache.clear()
    yield
    task_tool_module._subagent_usage_cache.clear()


@pytest.mark.asyncio
async def test_bridge_attaches_usage_to_dispatch_aimessage() -> None:
    """Subagent usage must merge into the dispatch AIMessage via reverse walk."""
    # Pre-populate cache as task_tool does on COMPLETED status
    task_tool_module._subagent_usage_cache["call-A"] = {
        "input_tokens": 100,
        "output_tokens": 50,
        "total_tokens": 150,
    }

    dispatch = AIMessage(
        content="",
        id="dispatch-msg-1",
        tool_calls=[{"id": "call-A", "name": "task", "args": {}}],
    )
    tool = ToolMessage(content="Task Succeeded. Result: done", name="task", tool_call_id="call-A")
    final = AIMessage(content="All done.", id="final-msg")

    state = {
        "messages": [
            HumanMessage(content="hi", id="u1"),
            dispatch,
            tool,
            final,
        ]
    }

    mw = TokenUsageMiddleware()
    out = await mw.aafter_model(state, Runtime())
    assert out is not None
    msgs = out.get("messages", [])
    # The dispatch AIMessage must appear with merged usage_metadata
    merged = next((m for m in msgs if m.id == "dispatch-msg-1"), None)
    assert merged is not None
    usage = getattr(merged, "usage_metadata", None)
    assert usage is not None
    assert usage["input_tokens"] == 100
    assert usage["output_tokens"] == 50
    assert usage["total_tokens"] == 150


@pytest.mark.asyncio
async def test_bridge_dedups_pop_consumes_cache_entry() -> None:
    """After the bridge runs, the cache entry must be popped."""
    task_tool_module._subagent_usage_cache["call-X"] = {
        "input_tokens": 3,
        "output_tokens": 1,
        "total_tokens": 4,
    }

    dispatch = AIMessage(
        content="",
        tool_calls=[{"id": "call-X", "name": "task", "args": {}}],
    )
    tool = ToolMessage(content="done", name="task", tool_call_id="call-X")
    final = AIMessage(content="final")

    state = {"messages": [HumanMessage(content="x"), dispatch, tool, final]}
    mw = TokenUsageMiddleware()
    await mw.aafter_model(state, Runtime())
    # Cache must be popped (P3.4 contract: pop_cached_subagent_usage is called)
    assert task_tool_module.pop_cached_subagent_usage("call-X") is None


@pytest.mark.asyncio
async def test_bridge_handles_no_task_messages() -> None:
    """If no ToolMessage with a cached usage exists, the middleware is a no-op."""
    final = AIMessage(content="plain")
    state = {"messages": [HumanMessage(content="x"), final]}
    mw = TokenUsageMiddleware()
    out = await mw.aafter_model(state, Runtime())
    # Should still emit token_usage in the response (existing behavior preserved)
    assert out is None or out.get("messages") is None
