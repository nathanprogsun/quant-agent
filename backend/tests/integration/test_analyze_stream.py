"""Analyze SSE stream integration tests."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

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
async def analyze_client(test_app_context):
    app = get_app()
    app.state.app_context = test_app_context
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
        yield client


@pytest.mark.asyncio
async def test_analyze_stream_emits_delta_and_done(analyze_client: APITestClient) -> None:
    async def fake_analyze(*_args: Any, **_kwargs: Any):
        yield "## 对标 DC42\n\n"
        yield "分析完成"

    mock_analyzer = AsyncMock()
    mock_analyzer.analyze = fake_analyze

    with patch("app.web.api.analyze.views._build_analyzer", return_value=mock_analyzer):
        async with analyze_client._client.stream(
            "POST",
            "/api/v1/analyze/stream",
            json={
                "thread_id": str(uuid4()),
                "backtest_id": "bt_1",
                "code": "def initialize(context): pass",
                "metrics": {"annual_return": 0.15, "sharpe": 1.2},
            },
        ) as resp:
            assert resp.status_code == 200
            body = await resp.aread()
            events = _parse_sse_messages(body.decode())

    types = [event["type"] for event in events]
    assert "analyze_delta" in types
    assert types[-1] == "analyze_done"
    assert any("DC42" in (event.get("content") or "") for event in events if event["type"] == "analyze_delta")
