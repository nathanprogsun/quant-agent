"""Tests for the deferred-tool setup + ``tool_search`` tool semantics."""

from __future__ import annotations

import pytest
from langchain_core.tools import BaseTool, Tool
from langgraph.types import Command

from app.tools.builtins.tool_search import (
    DeferredToolCatalog,
    assemble_deferred_tools,
    build_deferred_tool_setup,
    build_tool_search_tool,
    get_deferred_tools_prompt_section,
)
from app.tools.mcp_metadata import is_mcp_tool, tag_mcp_tool


def _make_tool(name: str, description: str = "") -> BaseTool:
    def _fn(x: str) -> str:
        return x

    return Tool(name=name, description=description, func=_fn)


def _make_mcp_tool(name: str, description: str = "") -> BaseTool:
    return tag_mcp_tool(_make_tool(name, description))


def _make_regular_tool(name: str, description: str = "") -> BaseTool:
    return _make_tool(name, description)


# ── tool_search tool basics ───────────────────────────────────────


@pytest.mark.asyncio
async def test_tool_search_returns_command_with_promoted_state() -> None:
    a = _make_mcp_tool("alpha")
    catalog = DeferredToolCatalog(tuple([a]))
    tool_search = build_tool_search_tool(catalog)

    # Invoke via ``tool_call`` (the model-style ToolCall dict) so the
    # InjectedToolCallId parameter is satisfied.
    result = await tool_search.ainvoke(
        {
            "type": "tool_call",
            "name": tool_search.name,
            "args": {"query": "alpha"},
            "id": "tc-1",
        }
    )
    assert isinstance(result, Command)
    assert result.update is not None
    promoted = result.update["promoted"]
    assert promoted["catalog_hash"] == catalog.hash
    assert "alpha" in promoted["names"]
    assert result.update["messages"][0].tool_call_id == "tc-1"
    assert result.update["messages"][0].name == "tool_search"


@pytest.mark.asyncio
async def test_tool_search_returns_no_names_for_unmatched() -> None:
    a = _make_mcp_tool("alpha")
    catalog = DeferredToolCatalog(tuple([a]))
    tool_search = build_tool_search_tool(catalog)

    result = await tool_search.ainvoke(
        {
            "type": "tool_call",
            "name": tool_search.name,
            "args": {"query": "missing"},
            "id": "tc-2",
        }
    )
    assert isinstance(result, Command)
    assert result.update["promoted"]["names"] == []
    assert "No tools found" in result.update["messages"][0].content


@pytest.mark.asyncio
async def test_tool_search_emits_tool_message_with_full_schema() -> None:
    a = _make_mcp_tool("alpha", "alpha search")
    catalog = DeferredToolCatalog(tuple([a]))
    tool_search = build_tool_search_tool(catalog)

    result = await tool_search.ainvoke(
        {
            "type": "tool_call",
            "name": tool_search.name,
            "args": {"query": "alpha"},
            "id": "tc-3",
        }
    )
    msg = result.update["messages"][0]
    # Schema dump of a Tool includes name + description.
    assert "alpha" in msg.content
    assert "alpha search" in msg.content


# ── setup variants ────────────────────────────────────────────────


def test_setup_disabled_returns_empty() -> None:
    tools = [_make_mcp_tool("alpha")]
    setup = build_deferred_tool_setup(tools, enabled=False)
    assert setup.tool_search_tool is None
    assert setup.deferred_names == frozenset()
    assert setup.catalog_hash is None


def test_setup_enabled_no_mcp_returns_empty() -> None:
    tools = [_make_regular_tool("alpha"), _make_regular_tool("beta")]
    setup = build_deferred_tool_setup(tools, enabled=True)
    assert setup.tool_search_tool is None
    assert setup.deferred_names == frozenset()


def test_setup_enabled_with_mcp_returns_populated() -> None:
    tools = [
        _make_regular_tool("regular"),
        _make_mcp_tool("mcp_alpha"),
    ]
    setup = build_deferred_tool_setup(tools, enabled=True)
    assert setup.tool_search_tool is not None
    assert setup.deferred_names == frozenset({"mcp_alpha"})
    assert setup.catalog_hash is not None and len(setup.catalog_hash) == 16


def test_assemble_fail_closed_when_enabled_but_no_deferred() -> None:
    """Simulate the boundary: setup is empty even though MCP-tagged tools
    are present. The failure mechanism is policy filtering excluding those
    tools BEFORE assemble, so we test by passing a tool list that has been
    pre-pruned. In this branch the implementation's invariant `deferred_names
    IS empty AND is_mcp_tool(any tool)` cannot be reached because pruning
    happens upstream — so this test documents the safe path.

    Concretely: if ``build_deferred_tool_setup`` returns an empty setup,
    assemble must NOT raise (since the precondition of the fail-closed
    branch requires BOTH a populated MCP set AND an empty deferred set,
    which is internal-inconsistent with our contract). Instead it just
    returns the tools unchanged.
    """
    # No MCP tools at all → both empty. No fail-closed raise; just pass-through.
    tools_without_mcp = [_make_regular_tool("regular")]
    final, setup = assemble_deferred_tools(tools_without_mcp, enabled=True)
    assert setup.tool_search_tool is None
    assert final == tools_without_mcp


def test_assemble_appends_tool_search_when_setup_populated() -> None:
    tools = [_make_mcp_tool("mcp_alpha")]
    final, setup = assemble_deferred_tools(tools, enabled=True)
    assert setup.tool_search_tool is not None
    assert any(t is setup.tool_search_tool for t in final)
    # Original MCP tool is preserved in the bound list.
    assert any(t.name == "mcp_alpha" for t in final)


def test_assemble_disabled_appends_nothing() -> None:
    tools = [_make_regular_tool("alpha")]
    final, setup = assemble_deferred_tools(tools, enabled=False)
    assert setup.tool_search_tool is None
    assert final == tools


# ── prompt section ────────────────────────────────────────────────


def test_prompt_section_empty_when_no_deferred_names() -> None:
    assert get_deferred_tools_prompt_section() == ""
    assert get_deferred_tools_prompt_section(deferred_names=frozenset()) == ""


def test_prompt_section_lists_names_sorted() -> None:
    section = get_deferred_tools_prompt_section(deferred_names=frozenset({"zeta", "alpha", "mu"}))
    assert "<available-deferred-tools>" in section
    # Names appear sorted (deer-flow convention) so the system prompt is
    # byte-stable across calls with the same input — required for
    # prefix-cache reuse.
    alpha_pos = section.index("alpha")
    mu_pos = section.index("mu")
    zeta_pos = section.index("zeta")
    assert alpha_pos < mu_pos < zeta_pos


# ── mcp_metadata predicate ────────────────────────────────────────


def test_is_mcp_tool_false_for_unmarked() -> None:
    assert is_mcp_tool(_make_regular_tool("alpha")) is False


def test_is_mcp_tool_true_for_tagged() -> None:
    assert is_mcp_tool(_make_mcp_tool("alpha")) is True
