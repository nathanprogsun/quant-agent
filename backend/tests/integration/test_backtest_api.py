"""Backtest API integration tests."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.app_context.app_context import AppContext
from app.core.backtest.service import BacktestService
from app.core.backtest.types import (
    BacktestAbortResult,
    BacktestMetrics,
    BacktestResultDetail,
    BacktestStatus,
)
from app.web.api.backtest.views import get_backtest_service
from app.web.application import get_app
from tests.integration.client import APITestClient


def _build_done_detail() -> BacktestResultDetail:
    """Build a typed BacktestResultDetail for a finished backtest."""
    return BacktestResultDetail(
        backtest_id="bt_12345",
        status=BacktestStatus.DONE,
        metrics=BacktestMetrics(annual_return=0.15, sharpe=1.2),
        performance=[],
        trades=[],
        holdings=[],
    )


def _build_abort_result(success: bool) -> BacktestAbortResult:
    return BacktestAbortResult(
        success=success,
        message="回测已终止" if success else "回测无法终止",
    )


@pytest.fixture
async def backtest_api_client(
    test_app_context: AppContext,
) -> AsyncGenerator[tuple[APITestClient, AsyncMock]]:
    """API client with BacktestService dependency overridden and auth."""
    svc = AsyncMock(spec=BacktestService)
    app = get_app()
    app.state.app_context = test_app_context
    app.dependency_overrides[get_backtest_service] = lambda: svc
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        client = APITestClient(ac)
        await client.post("/api/v1/auth/register", json={
            "email": f"{uuid4()}@test.com",
            "password": "TestPassword123!",
            "full_name": "Test User",
        })
        yield client, svc
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_submit_backtest_returns_id(
    backtest_api_client: tuple[APITestClient, AsyncMock],
) -> None:
    """POST /api/v1/backtest should return backtest_id."""
    client, svc = backtest_api_client
    svc.submit_for_user.return_value = "bt_12345"

    data = await client.post(
        "/api/v1/backtest",
        json={
            "code": "def initialize(context): pass",
            "thread_id": str(uuid4()),
            "version": 1,
            "params": {"start_date": "2020-01-01", "end_date": "2024-12-31"},
        },
    )

    assert data["backtest_id"] == "bt_12345"


@pytest.mark.asyncio
async def test_get_backtest_result(
    backtest_api_client: tuple[APITestClient, AsyncMock],
) -> None:
    """GET /api/v1/backtest/{id} should return backtest result."""
    client, svc = backtest_api_client
    svc.get_result_detail_for_user.return_value = _build_done_detail()
    data = await client.get("/api/v1/backtest/bt_12345")

    assert data["status"] == "done"
    assert data["backtest_id"] == "bt_12345"


@pytest.mark.asyncio
async def test_abort_backtest(
    backtest_api_client: tuple[APITestClient, AsyncMock],
) -> None:
    """POST /api/v1/backtest/{id}/abort should abort backtest."""
    client, svc = backtest_api_client
    svc.abort_for_user.return_value = _build_abort_result(success=True)
    data = await client.post("/api/v1/backtest/bt_12345/abort")

    assert data["success"] is True
