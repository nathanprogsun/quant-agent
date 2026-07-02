"""Tests for ``DeferredToolFilterMiddleware``."""

from __future__ import annotations

import asyncio

from langchain_core.messages import ToolMessage
from langchain_core.tools import Tool

from app.core.chat.agent.model_call import ModelCallRequest
from app.core.chat.middlewares.deferred_tool_filter_middleware import (
    DeferredToolFilterMiddleware,
)


def _make_tool(name: str, description: str = "") -> Tool:
    def _fn(x: str) -> str:
        return x

    return Tool(name=name, description=description, func=_fn)


def _mw() -> DeferredToolFilterMiddleware:
    return DeferredToolFilterMiddleware(
        deferred_names=frozenset({"mcp_a", "mcp_b"}),
        catalog_hash="h1",
    )


# ── model-call wrap ───────────────────────────────────────────────


def test_awrap_model_call_hides_all_deferred_when_no_promotion() -> None:
    mcp_a = _make_tool("mcp_a")
    mcp_b = _make_tool("mcp_b")
    active = _make_tool("active_c")
    request = ModelCallRequest(messages=[], tools=[mcp_a, mcp_b, active])

    seen: dict = {}

    async def handler(req):
        seen["tools"] = req.tools
        return "ok"

    result = asyncio.run(_mw().awrap_model_call(request, handler))
    assert result == "ok"
    assert [t.name for t in seen["tools"]] == ["active_c"]


def test_awrap_model_call_promoted_under_matching_hash_passes_through() -> None:
    mcp_a = _make_tool("mcp_a")
    mcp_b = _make_tool("mcp_b")
    active = _make_tool("active_c")
    # ModelCallRequest now carries ``state`` for filter checks.
    request = ModelCallRequest(
        messages=[],
        tools=[mcp_a, mcp_b, active],
        state={"promoted": {"catalog_hash": "h1", "names": ["mcp_a"]}},
    )

    seen: dict = {}

    async def handler(req):
        seen["tools"] = req.tools
        return "ok"

    asyncio.run(_mw().awrap_model_call(request, handler))
    assert {t.name for t in seen["tools"]} == {"mcp_a", "active_c"}


def test_awrap_model_call_promotion_ignored_when_hash_mismatches() -> None:
    mcp_a = _make_tool("mcp_a")
    mcp_b = _make_tool("mcp_b")
    active = _make_tool("active_c")
    request = ModelCallRequest(
        messages=[],
        tools=[mcp_a, mcp_b, active],
        state={"promoted": {"catalog_hash": "STALE", "names": ["mcp_a"]}},
    )

    seen: dict = {}

    async def handler(req):
        seen["tools"] = req.tools
        return "ok"

    asyncio.run(_mw().awrap_model_call(request, handler))
    assert [t.name for t in seen["tools"]] == ["active_c"]


def test_awrap_model_call_no_deferred_is_noop() -> None:
    active = _make_tool("active_c")
    mw = DeferredToolFilterMiddleware(frozenset(), "h1")
    request = ModelCallRequest(messages=[], tools=[active])

    seen: dict = {}

    async def handler(req):
        seen["tools"] = req.tools
        return "ok"

    asyncio.run(mw.awrap_model_call(request, handler))
    assert seen["tools"] is request.tools


def test_wrap_model_call_sync_variant_hides_deferred() -> None:
    mcp_a = _make_tool("mcp_a")
    active = _make_tool("active_c")
    request = ModelCallRequest(messages=[], tools=[mcp_a, active])

    seen: dict = {}

    def handler(req):
        seen["tools"] = req.tools
        return "ok"

    result = _mw().wrap_model_call(request, handler)
    assert result == "ok"
    assert [t.name for t in seen["tools"]] == ["active_c"]


# ── tool-call block ───────────────────────────────────────────────


def test_blocked_message_for_unpromoted_deferred_call() -> None:
    class _TCReq:
        tool_call = {"name": "mcp_a", "id": "tc1"}
        state = {}

    msg = _mw()._blocked_tool_message(_TCReq())
    assert isinstance(msg, ToolMessage)
    assert msg.status == "error"
    assert "tool_search" in msg.content
    assert msg.tool_call_id == "tc1"
    assert msg.name == "mcp_a"


def test_no_block_for_promoted_deferred_call() -> None:
    class _TCReq:
        tool_call = {"name": "mcp_a", "id": "tc1"}
        state = {"promoted": {"catalog_hash": "h1", "names": ["mcp_a"]}}

    assert _mw()._blocked_tool_message(_TCReq()) is None


def test_no_block_for_non_deferred_call() -> None:
    class _TCReq:
        tool_call = {"name": "active_c", "id": "tc1"}
        state = {}

    assert _mw()._blocked_tool_message(_TCReq()) is None


def test_no_block_when_no_deferred_names() -> None:
    class _TCReq:
        tool_call = {"name": "mcp_a", "id": "tc1"}
        state = {}

    mw = DeferredToolFilterMiddleware(frozenset(), "h1")
    assert mw._blocked_tool_message(_TCReq()) is None


def test_awrap_tool_call_returns_block_when_deferred() -> None:
    class _TCReq:
        tool_call = {"name": "mcp_a", "id": "tc1"}
        state = {}

    seen: dict = {}

    async def handler(req):
        seen["called"] = True
        return "would-have-run"

    out = asyncio.run(_mw().awrap_tool_call(_TCReq(), handler))
    assert isinstance(out, ToolMessage)
    assert out.status == "error"
    assert "called" not in seen


def test_awrap_tool_call_delegates_when_promoted() -> None:
    class _TCReq:
        tool_call = {"name": "mcp_a", "id": "tc1"}
        state = {"promoted": {"catalog_hash": "h1", "names": ["mcp_a"]}}

    seen: dict = {}

    async def handler(req):
        seen["called"] = True
        return "ok"

    out = asyncio.run(_mw().awrap_tool_call(_TCReq(), handler))
    assert out == "ok"
    assert seen["called"] is True


def test_awrap_tool_call_delegates_for_non_deferred_tool() -> None:
    class _TCReq:
        tool_call = {"name": "active_c", "id": "tc1"}
        state = {}

    async def handler(req):
        return "active-handled"

    out = asyncio.run(_mw().awrap_tool_call(_TCReq(), handler))
    assert out == "active-handled"
