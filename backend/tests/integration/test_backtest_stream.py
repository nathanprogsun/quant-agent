"""Backtest SSE stream integration tests."""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.backtest.service import BacktestService
from app.core.backtest.types import BacktestMetrics, BacktestResult, BacktestStatus
from app.settings import reload_settings
from app.web.api.backtest.views import get_backtest_service
from app.web.application import get_app
from tests.integration.client import APITestClient


def _parse_sse_messages(body: str) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    for block in body.split("\n\n"):
        for line in block.splitlines():
            if line.startswith("data:"):
                payload = line[len("data:") :].strip()
                if payload:
                    messages.append(json.loads(payload))
    return messages


@pytest.fixture
async def backtest_stream_client(
    test_app_context: Any, monkeypatch: pytest.MonkeyPatch
) -> AsyncGenerator[tuple[APITestClient, AsyncMock]]:
    """Authenticated client with mocked BacktestService and jqcli env."""
    monkeypatch.setenv("JQCLI_TOKEN", "test-token")
    reload_settings()

    poll_results = [
        BacktestResult(backtest_id="bt_stream_1", status=BacktestStatus.RUNNING),
        BacktestResult(
            backtest_id="bt_stream_1",
            status=BacktestStatus.DONE,
            metrics=BacktestMetrics(annual_return=0.12, sharpe=1.1),
        ),
    ]

    svc = AsyncMock(spec=BacktestService)
    svc.submit_for_user.return_value = "bt_stream_1"
    svc.poll_for_user.side_effect = poll_results

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
        yield client, svc

    app.dependency_overrides.clear()
    monkeypatch.delenv("JQCLI_TOKEN", raising=False)
    reload_settings()


@pytest.mark.asyncio
async def test_auth_check_unconfigured(
    noauthed_api_client: APITestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GET auth-check returns unconfigured when env vars missing."""
    monkeypatch.delenv("JQCLI_TOKEN", raising=False)
    monkeypatch.delenv("JQCLI_COOKIE", raising=False)
    reload_settings()

    await noauthed_api_client.post(
        "/api/v1/auth/register",
        json={
            "email": f"{uuid4()}@test.com",
            "password": "TestPassword123!",
            "full_name": "Test User",
        },
    )

    data = await noauthed_api_client.get("/api/v1/backtest/auth-check")
    assert data["configured"] is False
    assert data["authenticated"] is False


@pytest.mark.asyncio
async def test_backtest_sse_event_sequence(
    backtest_stream_client: tuple[APITestClient, AsyncMock],
) -> None:
    """Submit backtest then stream SSE progress/completed events."""
    client, _svc = backtest_stream_client
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
    backtest_id = submit["backtest_id"]

    with patch("app.core.backtest.worker.POLL_INTERVAL_SECONDS", 0.01):
        async with client._client.stream(
            "GET",
            f"/api/v1/backtest/{backtest_id}/stream",
        ) as resp:
            assert resp.status_code == 200
            body = await resp.aread()
            events = _parse_sse_messages(body.decode())

    event_types = [event["type"] for event in events]
    assert "backtest_started" in event_types
    assert "backtest_progress" in event_types
    assert "backtest_completed" in event_types
    completed = next(e for e in events if e["type"] == "backtest_completed")
    assert completed["metrics"]["annual_return"] == 0.12
