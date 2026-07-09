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
from app.web.application import get_app
from app.web.lifespan_service import backtest_service_from_request
from tests.integration.client import APITestClient


def _build_done_detail() -> BacktestResultDetail:
    """Build a typed BacktestResultDetail for a finished backtest."""
    return BacktestResultDetail(
        backtest_id="bt_12345",
        status=BacktestStatus.DONE,
        metrics=BacktestMetrics(annual_return=0.15, sharpe=1.2),
        performance=[],
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
    app.dependency_overrides[backtest_service_from_request] = lambda: svc
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        client = APITestClient(ac)
        await client.post(
            "/api/v1/auth/register",
            json={
                "email": f"{uuid4()}@test.com",
                "password": "TestPassword123!",
                "full_name": "Test User",
            },
        )
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


@pytest.mark.asyncio
async def test_cancel_thread_backtest(
    backtest_api_client: tuple[APITestClient, AsyncMock],
) -> None:
    """POST /api/v1/backtest/threads/{id}/cancel releases the thread lock."""
    client, svc = backtest_api_client
    thread_id = uuid4()
    svc.cancel_for_thread.return_value = "bt_stuck"

    data = await client.post(f"/api/v1/backtest/threads/{thread_id}/cancel")

    assert data["cancelled"] is True
    assert data["backtest_id"] == "bt_stuck"


@pytest.mark.asyncio
async def test_cancel_thread_backtest_no_active(
    backtest_api_client: tuple[APITestClient, AsyncMock],
) -> None:
    """Cancel returns cancelled=False when nothing is active."""
    client, svc = backtest_api_client
    svc.cancel_for_thread.return_value = None

    data = await client.post(f"/api/v1/backtest/threads/{uuid4()}/cancel")

    assert data["cancelled"] is False
