"""Tests for the deferred-tool catalog (``DeferredToolCatalog.search``)."""
from __future__ import annotations

from typing import Any

from langchain_core.tools import BaseTool, Tool

from app.tools.mcp_metadata import tag_mcp_tool
from app.tools.builtins.tool_search import MAX_RESULTS, DeferredToolCatalog


def _make_tool(name: str, description: str = "") -> BaseTool:
    """Create a ``Tool`` (the function-calling variant) with a fixed name."""

    def _fn(x: str) -> str:
        return x

    return Tool(name=name, description=description, func=_fn)


def test_select_exact_match() -> None:
    a = _make_tool("alpha", "a")
    b = _make_tool("beta", "b")
    c = _make_tool("gamma", "c")
    catalog = DeferredToolCatalog(tuple([a, b, c]))

    matched = catalog.search("select:alpha,beta")
    names = [t.name for t in matched]
    assert "alpha" in names
    assert "beta" in names
    assert "gamma" not in names


def test_plus_required_token_then_rank() -> None:
    slack_send = _make_tool("slack_send_message", "send via slack")
    slack_read = _make_tool("slack_read_channel", "read slack")
    unrelated = _make_tool("github_create_issue", "create github issue")
    catalog = DeferredToolCatalog(tuple([slack_send, slack_read, unrelated]))

    matched = catalog.search("+slack send")
    names = [t.name for t in matched]
    # Both slack_* are eligible (required=slack matches); send_message ranks
    # higher because description contains "send".
    assert names[0] == "slack_send_message"
    assert "slack_read_channel" in names
    assert "github_create_issue" not in names


def test_keyword_substring_fallback() -> None:
    notebook_new = _make_tool("notebook_create_cell", "create notebook cell")
    notebook_old = _make_tool("notebook_delete_cell", "delete notebook cell")
    irrelevant = _make_tool("slack_send", "send a slack message")
    catalog = DeferredToolCatalog(tuple([notebook_new, notebook_old, irrelevant]))

    matched = catalog.search("notebook")
    names = {t.name for t in matched}
    # The word "notebook" matches both notebook_* tools and the slack
    # description contains "notebook" substring, but only notebook_*
    # actually contain the term in their searchable text.
    assert "notebook_create_cell" in names
    assert "notebook_delete_cell" in names


def test_max_results_caps_returned() -> None:
    tools = [_make_tool(f"tool_{i:02d}") for i in range(20)]
    catalog = DeferredToolCatalog(tuple(tools))

    matched = catalog.search("tool")
    assert len(matched) <= MAX_RESULTS


def test_empty_query_returns_empty() -> None:
    a = _make_tool("alpha")
    catalog = DeferredToolCatalog(tuple([a]))
    assert catalog.search("") == []
    assert catalog.search("   ") == []


def test_invalid_regex_falls_back_to_literal() -> None:
    """Unbalanced parens ('[unclosed') must NOT crash the search."""
    a = _make_tool("alpha_search", "alpha search tool")
    b = _make_tool("beta_query", "another tool")
    catalog = DeferredToolCatalog(tuple([a, b]))
    # This regex is invalid; the loader must catch and fall back to a
    # literal substring match (no exception raised).
    matched = catalog.search("[unclosed")
    # The literal '[unclosed' is not in any tool name/description, so the
    # result is empty — but the call must succeed.
    assert matched == []


def test_literal_match_after_fallback() -> None:
    a = _make_tool("alpha_search", "alpha search")
    catalog = DeferredToolCatalog(tuple([a]))
    matched = catalog.search("alpha")
    assert any(t.name == "alpha_search" for t in matched)


def test_catalog_hash_stable_across_calls() -> None:
    a = tag_mcp_tool(_make_tool("alpha", "a"))
    b = tag_mcp_tool(_make_tool("beta", "b"))
    catalog = DeferredToolCatalog(tuple([a, b]))

    h1 = catalog.hash
    h2 = catalog.hash
    assert h1 == h2
    assert len(h1) == 16


def test_catalog_names_frozenset() -> None:
    a = tag_mcp_tool(_make_tool("alpha"))
    b = tag_mcp_tool(_make_tool("beta"))
    catalog = DeferredToolCatalog(tuple([a, b]))

    assert catalog.names == frozenset({"alpha", "beta"})


def test_search_runs_against_unmatched_tool_does_not_raise() -> None:
    """An invalid query must not raise — it just returns empty."""
    a = _make_tool("alpha")
    catalog = DeferredToolCatalog(tuple([a]))
    matched = catalog.search("[unclosed")
    assert isinstance(matched, list)


def test_catalog_search_prefers_name_match_in_relevance() -> None:
    """Substring search prefers tools whose NAME matches vs description match."""
    name_match = _make_tool("jupyter_run_cell", "execute")
    desc_match = _make_tool("python_evaluate", "jupyter evaluation")
    catalog = DeferredToolCatalog(tuple([name_match, desc_match]))

    matched = catalog.search("jupyter")
    assert matched[0].name == "jupyter_run_cell"
