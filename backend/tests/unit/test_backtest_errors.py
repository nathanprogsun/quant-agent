"""BacktestError maps jqcli exceptions to user-friendly errors."""

from __future__ import annotations

import pytest

from app.core.backtest.errors import BacktestError, map_jqcli_error
from jqcli.errors import ApiError, TimeoutError, NotAuthenticatedError, NetworkError


def test_map_api_error():
    err = ApiError("连接失败", status_code=500)
    result = map_jqcli_error(err)
    assert isinstance(result, BacktestError)
    assert "聚宽" in result.message or "API" in result.message
    assert result.error_code == "backtest_api_error"


def test_map_timeout_error():
    err = TimeoutError()
    result = map_jqcli_error(err)
    assert isinstance(result, BacktestError)
    assert result.error_code == "backtest_timeout"


def test_map_not_authenticated_error():
    err = NotAuthenticatedError()
    result = map_jqcli_error(err)
    assert isinstance(result, BacktestError)
    assert result.error_code == "backtest_not_authenticated"


def test_map_network_error():
    err = NetworkError()
    result = map_jqcli_error(err)
    assert isinstance(result, BacktestError)
    assert result.error_code == "backtest_network_error"


def test_map_unknown_error():
    err = RuntimeError("something")
    result = map_jqcli_error(err)
    assert isinstance(result, BacktestError)
    assert result.error_code == "backtest_unknown"
