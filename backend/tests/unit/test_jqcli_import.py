"""Verify jqcli package is importable and key functions exist."""

from __future__ import annotations

from jqcli.api.backtest import (
    get_backtest,
    get_backtest_result,
    get_backtest_stats,
    run_backtest,
)
from jqcli.errors import (
    ApiError,
    NotAuthenticatedError,
    TimeoutError,
)


def test_jqcli_api_backtest_importable() -> None:
    """jqcli.api.backtest functions should be importable."""

    assert callable(run_backtest)
    assert callable(get_backtest)
    assert callable(get_backtest_stats)
    assert callable(get_backtest_result)


def test_jqcli_errors_importable() -> None:
    """jqcli error classes should be importable."""

    assert issubclass(ApiError, Exception)
    assert issubclass(TimeoutError, Exception)
    assert issubclass(NotAuthenticatedError, Exception)



