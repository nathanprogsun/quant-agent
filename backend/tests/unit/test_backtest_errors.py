"""BacktestError maps jqcli exceptions to user-friendly errors."""

from __future__ import annotations

from jqcli.errors import (
    ApiError,
    NetworkError,
    NotAuthenticatedError,
    TimeoutError,
)

from app.core.backtest.errors import BacktestError, map_jqcli_error


def test_map_api_error() -> None:
    err = ApiError("连接失败", status_code=500)
    result = map_jqcli_error(err)
    assert isinstance(result, BacktestError)
    assert "聚宽" in result.message or "API" in result.message
    assert result.error_code == "backtest_api_error"


def test_map_timeout_error() -> None:
    err = TimeoutError()
    result = map_jqcli_error(err)
    assert isinstance(result, BacktestError)
    assert result.error_code == "backtest_timeout"


def test_map_not_authenticated_error() -> None:
    err = NotAuthenticatedError()
    result = map_jqcli_error(err)
    assert isinstance(result, BacktestError)
    assert result.error_code == "backtest_not_authenticated"


def test_map_network_error() -> None:
    err = NetworkError()
    result = map_jqcli_error(err)
    assert isinstance(result, BacktestError)
    assert result.error_code == "backtest_network_error"


def test_map_unknown_error() -> None:
    err = RuntimeError("something")
    result = map_jqcli_error(err)
    assert isinstance(result, BacktestError)
    assert result.error_code == "backtest_unknown"
