"""Backtest log SSE integration tests."""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.backtest.service import BacktestService
from app.core.backtest.types import (
    BacktestLogResult,
    BacktestMetrics,
    BacktestResult,
    BacktestStatus,
)
from app.settings import reload_settings
from app.web.application import get_app
from app.web.lifespan_service import backtest_service_from_request
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
async def backtest_log_sse_client(
    test_app_context: Any, monkeypatch: pytest.MonkeyPatch
) -> AsyncGenerator[tuple[APITestClient, AsyncMock]]:
    monkeypatch.setenv("JQCLI_USERNAME", "test-user")
    monkeypatch.setenv("JQCLI_PASSWORD", "test-pass")
    reload_settings()

    poll_results = [
        BacktestResult(backtest_id="bt_log_1", status=BacktestStatus.RUNNING),
        BacktestResult(
            backtest_id="bt_log_1",
            status=BacktestStatus.DONE,
            metrics=BacktestMetrics(
                annual_return=0.12,
                sharpe=1.1,
                raw={"total_return": 0.68, "algorithm_return": 0.68},
            ),
        ),
    ]

    svc = AsyncMock(spec=BacktestService)
    svc.submit_for_user.return_value = "bt_log_1"
    svc.poll_for_user.side_effect = poll_results
    svc.fetch_logs_incremental.return_value = BacktestLogResult(
        logs=["[12:00:01] INFO start", "[12:00:02] INFO running"],
        next_offset=2,
    )

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
    monkeypatch.delenv("JQCLI_USERNAME", raising=False)
    monkeypatch.delenv("JQCLI_PASSWORD", raising=False)
    reload_settings()


@pytest.mark.asyncio
async def test_backtest_sse_includes_log_lines(
    backtest_log_sse_client: tuple[APITestClient, AsyncMock],
) -> None:
    client, _svc = backtest_log_sse_client
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

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("app.core.backtest.worker.POLL_INTERVAL_SECONDS", 0.01)
        async with client._client.stream(
            "GET",
            f"/api/v1/backtest/{backtest_id}/stream",
        ) as resp:
            assert resp.status_code == 200
            body = await resp.aread()
            events = _parse_sse_messages(body.decode())

    log_events = [e for e in events if e.get("type") == "backtest_log_line"]
    print("DEBUG events:", events)
    assert len(log_events) >= 1
    assert "INFO" in log_events[0]["line"]

    completed = next(e for e in events if e["type"] == "backtest_completed")
    assert completed["metrics"]["total_return"] == 0.68
