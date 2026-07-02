"""BacktestService tests — mock jqcli API calls."""

from __future__ import annotations

from unittest.mock import patch
from uuid import uuid4

import pytest
from jqcli.errors import (
    ApiError,
    NotAuthenticatedError,
    TimeoutError,
)

from app.core.backtest.errors import BacktestError
from app.core.backtest.service import BacktestService
from app.core.backtest.types import AuthResult, BacktestParams, BacktestStatus


@pytest.fixture
def service() -> BacktestService:
    return BacktestService(
        token="test-token",
        cookie="test-cookie",
        api_base="https://www.joinquant.com",
    )


@pytest.mark.asyncio
async def test_check_auth_success(service: BacktestService) -> None:
    """check_auth should return AuthResult when authenticated."""
    with patch("app.core.backtest.service._check_auth_sync", return_value={"username": "testuser"}):
        result = await service.check_auth()
        assert isinstance(result, AuthResult)
        assert result.is_authenticated is True
        assert result.username == "testuser"


@pytest.mark.asyncio
async def test_check_auth_not_authenticated() -> None:
    """check_auth should handle NotAuthenticatedError."""
    svc = BacktestService(token="", cookie="", api_base="https://www.joinquant.com")
    with patch("app.core.backtest.service._check_auth_sync", side_effect=NotAuthenticatedError()):
        result = await svc.check_auth()
        assert result.is_authenticated is False


@pytest.mark.asyncio
async def test_submit_success(service: BacktestService) -> None:
    """submit should return backtest_id on success."""
    with patch("app.core.backtest.service._submit_sync", return_value="bt_12345"):
        result = await service.submit(
            code="def initialize(context): pass",
            thread_id=uuid4(),
            version=1,
            params=BacktestParams(),
        )
        assert result == "bt_12345"


@pytest.mark.asyncio
async def test_submit_api_error(service: BacktestService) -> None:
    """submit should raise BacktestError on ApiError."""
    with (
        patch(
            "app.core.backtest.service._submit_sync",
            side_effect=ApiError("server error", status_code=500),
        ),
        pytest.raises(BacktestError, match="聚宽"),
    ):
        await service.submit(code="code", thread_id=uuid4(), version=1, params=BacktestParams())


@pytest.mark.asyncio
async def test_poll_done(service: BacktestService) -> None:
    """poll should return DONE status when backtest completes."""
    with patch(
        "app.core.backtest.service._poll_sync",
        return_value={"status": "done", "metrics": {"annual_return": 0.15}},
    ):
        result = await service.poll("bt_12345")
        assert result.status == BacktestStatus.DONE
        assert result.metrics is not None
        assert result.metrics.annual_return == 0.15


@pytest.mark.asyncio
async def test_poll_timeout(service: BacktestService) -> None:
    """poll should raise BacktestError on timeout."""
    with (
        patch("app.core.backtest.service._poll_sync", side_effect=TimeoutError()),
        pytest.raises(BacktestError, match="超时"),
    ):
        await service.poll("bt_12345")
