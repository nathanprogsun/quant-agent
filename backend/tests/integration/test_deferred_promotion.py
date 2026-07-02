"""Integration test: tool_search -> promotion -> middleware exposes tool.

End-to-end check that the three pieces (catalog, tool_search tool,
deferred filter middleware) cooperate through a real LangGraph graph
state update.
"""

from __future__ import annotations

from typing import Any

import pytest
from langchain_core.messages import ToolMessage
from langchain_core.tools import Tool

from app.core.chat.agent.model_call import ModelCallRequest
from app.core.chat.middlewares.deferred_tool_filter_middleware import (
    DeferredToolFilterMiddleware,
)
from app.tools.builtins.tool_search import (
    DeferredToolCatalog,
    build_tool_search_tool,
)
from app.tools.mcp_metadata import tag_mcp_tool


def _make_mcp_tool(name: str) -> Tool:
    def _fn(x: str) -> str:
        return x

    inner = Tool(name=name, description=f"mcp tool {name}", func=_fn)
    return tag_mcp_tool(inner)


@pytest.mark.asyncio
async def test_promotion_via_tool_search_passes_to_middleware_filter() -> None:
    """Simulate the full flow:

    1. Catalog built from MCP tools; ``deferred_names = {alpha, beta}``.
    2. tool_search.Tool is invoked with query="alpha" → produces a Command
       with state.promoted.names = ["alpha"], catalog_hash matching.
    3. Filter middleware applied to a fresh request with the post-update
       state — alpha is now visible, beta stays hidden.
    """
    alpha = _make_mcp_tool("alpha")
    beta = _make_mcp_tool("beta")
    active = Tool(name="active", description="not deferred", func=lambda x: x)
    catalog = DeferredToolCatalog(tuple([alpha, beta]))
    mw = DeferredToolFilterMiddleware(catalog.names, catalog.hash)
    tool_search = build_tool_search_tool(catalog)

    # 1. Invoke tool_search.
    cmd = await tool_search.ainvoke(
        {
            "type": "tool_call",
            "name": tool_search.name,
            "args": {"query": "alpha"},
            "id": "tc-alpha",
        }
    )
    assert hasattr(cmd, "update")
    state = cmd.update
    promoted_state = state["promoted"]
    assert promoted_state["catalog_hash"] == catalog.hash
    assert promoted_state["names"] == ["alpha"]

    # 2. Apply the Command's update to graph state.
    graph_state: dict[str, Any] = {"promoted": promoted_state, "messages": []}

    # 3. Filter middleware sees the promotion.
    request = ModelCallRequest(
        messages=[],
        tools=[alpha, beta, active],
        state=graph_state,
    )

    seen: dict = {}

    async def handler(req):
        seen["tools"] = req.tools
        return "bound"

    result = await mw.awrap_model_call(request, handler)
    assert result == "bound"
    visible_names = {t.name for t in seen["tools"]}
    assert "alpha" in visible_names
    assert "active" in visible_names
    assert "beta" not in visible_names


@pytest.mark.asyncio
async def test_promotion_with_stale_hash_keeps_tools_hidden() -> None:
    """If the persisted ``promoted.catalog_hash`` doesn't match the
    middleware's hash, the promotion is ignored — protects against a
    renamed tool silently reappearing after a catalog refresh."""
    alpha = _make_mcp_tool("alpha")
    beta = _make_mcp_tool("beta")
    catalog = DeferredToolCatalog(tuple([alpha, beta]))
    mw = DeferredToolFilterMiddleware(catalog.names, catalog.hash)

    request = ModelCallRequest(
        messages=[],
        tools=[alpha, beta],
        state={"promoted": {"catalog_hash": "DELETED_HASH", "names": ["alpha"]}},
    )

    seen: dict = {}

    async def handler(req):
        seen["tools"] = req.tools
        return "bound"

    await mw.awrap_model_call(request, handler)
    assert seen["tools"] == []  # both deferred names still hidden


@pytest.mark.asyncio
async def test_tool_call_to_deferred_tool_without_promotion_is_blocked() -> None:
    """End-to-end: a model that bypassed the schema filter and called a
    deferred tool directly must receive an error ToolMessage, not crash."""
    alpha = _make_mcp_tool("alpha")
    catalog = DeferredToolCatalog(tuple([alpha]))
    mw = DeferredToolFilterMiddleware(catalog.names, catalog.hash)

    class _TCReq:
        tool_call = {"name": "alpha", "id": "tc-direct"}
        state = {}

    seen_called: dict = {}

    async def handler(req):
        seen_called["yes"] = True
        return "would-have-run"

    out = await mw.awrap_tool_call(_TCReq(), handler)
    assert isinstance(out, ToolMessage)
    assert out.status == "error"
    assert out.tool_call_id == "tc-direct"
    assert "tool_search" in out.content
    assert "yes" not in seen_called


@pytest.mark.asyncio
async def test_tool_call_to_promoted_deferred_tool_executes() -> None:
    alpha = _make_mcp_tool("alpha")
    catalog = DeferredToolCatalog(tuple([alpha]))
    mw = DeferredToolFilterMiddleware(catalog.names, catalog.hash)

    class _TCReq:
        tool_call = {"name": "alpha", "id": "tc-direct"}
        state = {"promoted": {"catalog_hash": catalog.hash, "names": ["alpha"]}}

    async def handler(req):
        return "executed"

    out = await mw.awrap_tool_call(_TCReq(), handler)
    assert out == "executed"
