"""param_tool dc42_ranges resolution tests."""

from __future__ import annotations

from app.core.chat.tools.builtin.param_tool import (
    make_validate_parameters_tool,
    resolve_dc42_ranges,
    validate_parameters,
)


def test_resolve_dc42_ranges_prefers_state():
    state = {"dc42_ranges": {"stock_count": {"P10": 1, "P90": 5}}}
    resolved = resolve_dc42_ranges(state, fallback={"other": {"P10": 0, "P90": 1}})
    assert resolved == state["dc42_ranges"]


def test_resolve_dc42_ranges_falls_back_to_defaults():
    resolved = resolve_dc42_ranges(None, fallback={"stock_count": {"P10": 2, "P90": 8}})
    assert resolved["stock_count"]["P90"] == 8


def test_validate_parameters_without_explicit_ranges_still_works():
    result = validate_parameters(
        params={"stock_count": 100},
        dc42_ranges={"stock_count": {"P10": 3, "P50": 10, "P90": 30}},
    )
    assert result.warnings


def test_tool_uses_state_dc42_ranges_when_present():
    tool = make_validate_parameters_tool(
        dc42_ranges={"stock_count": {"P10": 3, "P50": 10, "P90": 30}},
    )
    assert tool.name == "validate_strategy_parameters"
