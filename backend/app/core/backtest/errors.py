"""Backtest exception mapping."""

from __future__ import annotations

from http import HTTPStatus
from typing import Any

from app.common.exception.exception import ApplicationError
from jqcli.errors import (
    ApiError,
    NetworkError,
    NotAuthenticatedError,
    TimeoutError,
    JqcliError,
)


class BacktestError(ApplicationError):
    """Unified backtest error — wraps all jqcli exceptions."""

    def __init__(self, message: str, code: str = "backtest_error") -> None:
        self.error_code = code
        self.message = message
        super().__init__(message)

    def http_code(self) -> int:
        return HTTPStatus.INTERNAL_SERVER_ERROR


def map_jqcli_error(error: Exception) -> BacktestError:
    """Map a jqcli exception to a BacktestError with Chinese message."""
    if isinstance(error, NotAuthenticatedError):
        return BacktestError(
            message="未登录聚宽，请先在设置中配置认证信息",
            code="backtest_not_authenticated",
        )
    if isinstance(error, TimeoutError):
        return BacktestError(
            message="回测超时，请稍后查看结果或缩短回测时间范围",
            code="backtest_timeout",
        )
    if isinstance(error, NetworkError):
        return BacktestError(
            message="无法连接到聚宽服务器，请检查网络",
            code="backtest_network_error",
        )
    if isinstance(error, ApiError):
        return BacktestError(
            message=f"聚宽 API 错误: {error.message}",
            code="backtest_api_error",
        )
    if isinstance(error, JqcliError):
        return BacktestError(
            message=f"回测错误: {error.message}",
            code="backtest_jqcli_error",
        )
    return BacktestError(
        message=f"回测发生未知错误: {error!s}",
        code="backtest_unknown",
    )
