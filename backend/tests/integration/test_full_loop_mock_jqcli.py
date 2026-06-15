"""Full loop integration test with mocked jqcli."""

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


@pytest.mark.asyncio
async def test_full_loop_submit_backtest_and_analyze_mocked(
    test_app_context,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("JQCLI_TOKEN", "test-token")

    svc = AsyncMock(spec=BacktestService)
    svc.submit.return_value = "bt_loop_1"
    svc.poll.return_value = BacktestResult(
        backtest_id="bt_loop_1",
        status=BacktestStatus.DONE,
        metrics=BacktestMetrics(annual_return=0.18, sharpe=1.3),
    )

    async def fake_analyze(*_args, **_kwargs):
        yield "mock analysis"

    mock_analyzer = AsyncMock()
    mock_analyzer.analyze = fake_analyze

    app = get_app()
    app.state.app_context = test_app_context
    app.dependency_overrides[get_backtest_service] = lambda: svc

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

        thread_id = str(uuid4())
        submit = await client.post(
            "/api/v1/backtest",
            json={
                "code": "def initialize(context): pass",
                "thread_id": thread_id,
                "version": 1,
                "params": {"start_date": "2020-01-01", "end_date": "2024-12-31"},
            },
        )
        assert submit["backtest_id"] == "bt_loop_1"

        with patch("app.web.api.analyze.views._build_analyzer", return_value=mock_analyzer):
            async with client._client.stream(
                "POST",
                "/api/v1/analyze/stream",
                json={
                    "thread_id": thread_id,
                    "backtest_id": "bt_loop_1",
                    "code": "def initialize(context): pass",
                    "metrics": {"annual_return": 0.18, "sharpe": 1.3},
                },
            ) as resp:
                assert resp.status_code == 200
                body = await resp.aread()
                assert b"analyze_done" in body

    app.dependency_overrides.clear()
