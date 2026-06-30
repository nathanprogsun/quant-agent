"""Integration tests for backtest SSE ownership flow.

These exercise the bug where each request's ``Depends(backtest_service_from_request)``
constructed a fresh ``BacktestService`` (and therefore a fresh
``BacktestRegistry``). The SSE stream endpoint's fresh registry could never
find the just-submitted backtest, so the SSE handshake returned 404 and the
client never received any log / progress / completion events.

After the fix, both endpoints resolve the *same* ``AppContext.backtest_registry``
and the SSE stream returns 200 + events.
"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from typing import Any
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.backtest.registry import BacktestRegistry
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
async def backtest_sse_e2e_client(
    test_app_context: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncGenerator[tuple[APITestClient, BacktestService]]:
    """End-to-end client with real registry wiring.

    Overrides only ``backtest_service_from_request`` to inject a *shared* registry-backed
    service, mimicking the post-fix request flow. Every dependency call reuses
    the same registry instance — exactly what the fix achieves in production.
    """
    monkeypatch.setenv("JQCLI_USERNAME", "e2e-user")
    monkeypatch.setenv("JQCLI_PASSWORD", "e2e-pass")
    reload_settings()

    shared_registry = test_app_context.backtest_registry
    assert shared_registry is not None, "test_app_context must wire backtest_registry"

    # Pre-seeded ownership pattern: the worker / submit path will populate it.
    async def _submit_for_user(
        user_id: Any,
        thread_id: Any,
        code: str,
        version: int,
        params: Any,
    ) -> str:
        backtest_id = f"bt-{uuid4().hex[:8]}"
        shared_registry.register(backtest_id, user_id, thread_id=str(thread_id))
        return backtest_id

    poll_calls: list[str] = []

    async def _poll_for_user(backtest_id: str, user_id: Any) -> BacktestResult:
        poll_calls.append(backtest_id)
        if len(poll_calls) == 1:
            return BacktestResult(backtest_id=backtest_id, status=BacktestStatus.RUNNING)
        return BacktestResult(
            backtest_id=backtest_id,
            status=BacktestStatus.DONE,
            metrics=BacktestMetrics(annual_return=0.2, sharpe=1.4),
        )

    log_calls: list[tuple[str, int]] = []

    async def _fetch_logs(self: Any, backtest_id: str, offset: int = 0) -> BacktestLogResult:
        log_calls.append((backtest_id, offset))
        return BacktestLogResult(
            logs=["[12:00:01] INFO running"],
            next_offset=offset + 1,
        )

    # Build a real BacktestService instance, sharing the registry.
    service = BacktestService(
        token="t",
        cookie="c",
        api_base="https://example",
        registry=shared_registry,
    )
    service.submit_for_user = _submit_for_user  # type: ignore[method-assign]
    service.poll_for_user = _poll_for_user  # type: ignore[method-assign]
    service.fetch_logs_incremental = _fetch_logs  # type: ignore[assignment]

    app = get_app()
    app.state.app_context = test_app_context
    app.dependency_overrides[backtest_service_from_request] = lambda: service

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        client = APITestClient(ac)
        await client.post(
            "/api/v1/auth/register",
            json={
                "email": f"{uuid4()}@test.com",
                "password": "TestPassword123!",
                "full_name": "E2E User",
            },
        )
        yield client, service

    app.dependency_overrides.clear()
    monkeypatch.delenv("JQCLI_USERNAME", raising=False)
    monkeypatch.delenv("JQCLI_PASSWORD", raising=False)
    reload_settings()


@pytest.mark.asyncio
async def test_sse_stream_finds_backtest_submitted_in_prior_request(
    backtest_sse_e2e_client: tuple[APITestClient, BacktestService],
) -> None:
    """The core regression test.

    Submit + GET .../stream are two independent FastAPI requests, each of
    which constructs its own ``BacktestService`` via dependency injection.
    Both must see the same ownership registry, otherwise the SSE handshake
    returns 404 and the client receives no events.
    """
    client, _service = backtest_sse_e2e_client
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
    assert submit["backtest_id"], "submit must return a backtest id"
    backtest_id = submit["backtest_id"]

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("app.core.backtest.worker.POLL_INTERVAL_SECONDS", 0.01)
        async with client._client.stream(
            "GET",
            f"/api/v1/backtest/{backtest_id}/stream",
        ) as resp:
            assert resp.status_code == 200, (
                "SSE must accept the request — the bug returned 404 because"
                " the per-request service had a fresh registry that didn't see"
                " the submit"
            )
            body = await resp.aread()

    events = _parse_sse_messages(body.decode())
    event_types = [e["type"] for e in events]
    assert "backtest_started" in event_types
    assert "backtest_completed" in event_types

    completed = next(e for e in events if e["type"] == "backtest_completed")
    assert completed["metrics"]["annual_return"] == 0.2


@pytest.mark.asyncio
async def test_sse_stream_returns_404_for_backtest_owned_by_another_user(
    backtest_sse_e2e_client: tuple[APITestClient, BacktestService],
    test_app_context: Any,
) -> None:
    """Ownership is enforced: a different user cannot read someone else's stream."""
    client, _service = backtest_sse_e2e_client
    shared_registry: BacktestRegistry = test_app_context.backtest_registry

    other_user_id = uuid4()
    shared_registry.register("bt-other-user", other_user_id)

    resp = await client._client.get("/api/v1/backtest/bt-other-user/stream")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_sse_stream_returns_404_for_unknown_backtest(
    backtest_sse_e2e_client: tuple[APITestClient, BacktestService],
) -> None:
    """Asking for an unknown backtest id must 404 — registry lookup is the gate."""
    client, _service = backtest_sse_e2e_client
    resp = await client._client.get("/api/v1/backtest/bt-nonexistent/stream")
    assert resp.status_code == 404
