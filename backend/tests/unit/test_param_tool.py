"""validate_parameters agent tool tests."""

from __future__ import annotations

from app.core.chat.tools.builtin.param_tool import validate_parameters


def test_validate_positive_param_has_no_warning() -> None:
    """Sanity-checked positive parameters should pass."""
    result = validate_parameters(params={"stock_count": 5})
    assert len(result.warnings) == 0


def test_validate_negative_param_warns() -> None:
    """Negative parameters should warn."""
    result = validate_parameters(params={"lookback": -1})
    assert len(result.warnings) > 0
    assert "lookback" in result.warnings[0]


def test_validate_zero_critical_param_warns() -> None:
    """Zero for known critical params should warn."""
    result = validate_parameters(params={"stock_count": 0})
    assert len(result.warnings) > 0
    assert "stock_count" in result.warnings[0]


def test_validate_unknown_param_is_silent() -> None:
    """Unknown parameters should be noted but not warned."""
    result = validate_parameters(params={"custom_param": 42})
    assert len(result.warnings) == 0
