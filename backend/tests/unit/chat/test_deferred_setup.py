"""Tests for the deferred-tool build site that ``make_lead_agent`` invokes."""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.tools import Tool

from app.tools.builtins.tool_search import (
    DeferredToolSetup,
    assemble_deferred_tools,
    build_deferred_tool_setup,
)
from app.tools.mcp_metadata import tag_mcp_tool


def _make_tool(name: str, description: str = ""):
    def _fn(x: str) -> str:
        return x

    return Tool(name=name, description=description, func=_fn)


def _make_mcp(name: str):
    return tag_mcp_tool(_make_tool(name))


# ── build_deferred_tool_setup ─────────────────────────────────────


def test_returns_empty_when_disabled() -> None:
    setup = build_deferred_tool_setup([_make_mcp("alpha")], enabled=False)
    assert setup.tool_search_tool is None
    assert setup.deferred_names == frozenset()
    assert setup.catalog_hash is None


def test_returns_empty_when_enabled_but_no_mcp_tools() -> None:
    setup = build_deferred_tool_setup(
        [_make_tool("alpha"), _make_tool("beta")], enabled=True
    )
    assert setup.tool_search_tool is None


def test_returns_populated_with_mcp_tools() -> None:
    tools = [_make_tool("regular"), _make_mcp("mcp_alpha"), _make_mcp("mcp_beta")]
    setup = build_deferred_tool_setup(tools, enabled=True)
    assert setup.tool_search_tool is not None
    assert setup.deferred_names == frozenset({"mcp_alpha", "mcp_beta"})
    assert setup.catalog_hash is not None


def test_catalog_hash_changes_on_tool_set_change() -> None:
    s1 = build_deferred_tool_setup([_make_mcp("alpha")], enabled=True)
    s2 = build_deferred_tool_setup([_make_mcp("alpha"), _make_mcp("beta")], enabled=True)
    assert s1.catalog_hash != s2.catalog_hash


# ── assemble_deferred_tools ───────────────────────────────────────


def test_assemble_disabled_passthrough() -> None:
    tools = [_make_tool("alpha")]
    final, setup = assemble_deferred_tools(tools, enabled=False)
    assert setup.tool_search_tool is None
    assert final == tools


def test_assemble_enabled_appends_tool_search() -> None:
    tools = [_make_tool("regular"), _make_mcp("mcp_alpha")]
    final, setup = assemble_deferred_tools(tools, enabled=True)
    assert setup.tool_search_tool is not None
    assert setup.tool_search_tool in final
    # All originals still present.
    assert any(t.name == "regular" for t in final)
    assert any(t.name == "mcp_alpha" for t in final)


def test_assemble_enabled_empty_after_filtering_passthrough() -> None:
    """No MCP after filtering → no tool_search, no raise."""
    tools = [_make_tool("regular")]
    final, setup = assemble_deferred_tools(tools, enabled=True)
    assert setup.tool_search_tool is None
    assert final == tools


# ── invariants ────────────────────────────────────────────────────


def test_invariant_tool_search_none_matches_empty_deferred() -> None:
    """Empty setup has all three fields matching the empty invariant."""
    setup = build_deferred_tool_setup([], enabled=True)
    assert setup.tool_search_tool is None
    assert setup.deferred_names == frozenset()
    assert setup.catalog_hash is None


def test_populated_setup_has_three_fields_set() -> None:
    setup = build_deferred_tool_setup([_make_mcp("alpha")], enabled=True)
    assert setup.tool_search_tool is not None
    assert setup.deferred_names != frozenset()
    assert setup.catalog_hash is not None
    # Tool count and deferred-names count match.
    assert len(setup.deferred_names) == 1


# ── prompt-section helper ─────────────────────────────────────────


def test_prompt_section_round_trip() -> None:
    from app.tools.builtins.tool_search import get_deferred_tools_prompt_section

    section = get_deferred_tools_prompt_section(
        deferred_names=frozenset({"alpha", "beta"})
    )
    assert "alpha" in section
    assert "beta" in section
    assert "<available-deferred-tools>" in section


def test_prompt_section_byte_stable() -> None:
    """Same input → same string."""
    from app.tools.builtins.tool_search import get_deferred_tools_prompt_section

    s1 = get_deferred_tools_prompt_section(deferred_names=frozenset({"x", "y"}))
    s2 = get_deferred_tools_prompt_section(deferred_names=frozenset({"y", "x"}))
    assert s1 == s2  # sorted internally — order-independent
