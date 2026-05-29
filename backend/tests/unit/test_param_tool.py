"""validate_parameters agent tool tests."""

from __future__ import annotations

from app.core.chat.tools.builtin.param_tool import validate_parameters


def test_validate_in_range():
    """Parameters within DC42 range should pass."""
    result = validate_parameters(
        params={"stock_count": 5},
        dc42_ranges={"stock_count": {"P10": 3, "P50": 10, "P90": 30}},
    )
    assert len(result.warnings) == 0


def test_validate_out_of_range():
    """Parameters outside DC42 range should warn."""
    result = validate_parameters(
        params={"stock_count": 100},
        dc42_ranges={"stock_count": {"P10": 3, "P50": 10, "P90": 30}},
    )
    assert len(result.warnings) > 0
    assert "stock_count" in result.warnings[0]


def test_validate_unknown_param():
    """Unknown parameters should be noted but not warned."""
    result = validate_parameters(
        params={"custom_param": 42},
        dc42_ranges={"stock_count": {"P10": 3, "P50": 10, "P90": 30}},
    )
    assert len(result.warnings) == 0
