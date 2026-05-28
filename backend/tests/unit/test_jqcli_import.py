"""Verify jqcli package is importable and key functions exist."""

from __future__ import annotations

import pytest


def test_jqcli_api_backtest_importable():
    """jqcli.api.backtest functions should be importable."""
    from jqcli.api.backtest import (
        run_backtest,
        get_backtest,
        get_backtest_stats,
        get_backtest_result,
    )
    assert callable(run_backtest)
    assert callable(get_backtest)
    assert callable(get_backtest_stats)
    assert callable(get_backtest_result)


def test_jqcli_errors_importable():
    """jqcli error classes should be importable."""
    from jqcli.errors import (
        ApiError,
        TimeoutError,
        NotAuthenticatedError,
        NetworkError,
    )
    assert issubclass(ApiError, Exception)
    assert issubclass(TimeoutError, Exception)
    assert issubclass(NotAuthenticatedError, Exception)


def test_jqcli_client_importable():
    """jqcli.api.client.ApiClient should be importable."""
    from jqcli.api.client import ApiClient
    assert ApiClient is not None
