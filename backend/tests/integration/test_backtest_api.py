"""Backtest API integration tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.backtest.service import BacktestService
from app.core.backtest.types import BacktestMetrics, BacktestResult, BacktestStatus
from app.web.api.backtest.views import get_backtest_service
from app.web.application import get_app
from tests.integration.client import APITestClient


@pytest.fixture
async def backtest_api_client(test_app_context):
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
async def test_submit_backtest_returns_id(backtest_api_client) -> None:
    """POST /api/v1/backtest should return backtest_id."""
    client, svc = backtest_api_client
    svc.submit.return_value = "bt_12345"

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
async def test_get_backtest_result(backtest_api_client) -> None:
    """GET /api/v1/backtest/{id} should return backtest result."""
    client, svc = backtest_api_client
    svc.poll.return_value = BacktestResult(
        backtest_id="bt_12345",
        status=BacktestStatus.DONE,
        metrics=BacktestMetrics(annual_return=0.15, sharpe=1.2),
    )
    with patch("app.web.api.backtest.views._assert_owner"):
        data = await client.get("/api/v1/backtest/bt_12345")

    assert data["status"] == "done"
    assert data["backtest_id"] == "bt_12345"


@pytest.mark.asyncio
async def test_abort_backtest(backtest_api_client) -> None:
    """POST /api/v1/backtest/{id}/abort should abort backtest."""
    client, svc = backtest_api_client
    svc.abort.return_value = True
    with patch("app.web.api.backtest.views._assert_owner"):
        data = await client.post("/api/v1/backtest/bt_12345/abort")

    assert data["success"] is True
