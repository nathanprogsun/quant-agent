"""Integration tests for health endpoint."""
from __future__ import annotations

import pytest

from tests.integration.client import APITestClient


@pytest.fixture
def health_client(api_client) -> APITestClient:
    """Health check client (no auth needed)."""
    return APITestClient(api_client)


@pytest.mark.asyncio
async def test_health_check(health_client: APITestClient) -> None:
    """Health endpoint returns 200."""
    status, data = await health_client.get_raw("/health")
    assert status == 200
    assert data["status"] == "healthy"


@pytest.mark.asyncio
async def test_health_check_status_ok(health_client: APITestClient) -> None:
    """Health endpoint returns status OK."""
    status, data = await health_client.get_raw("/health")
    assert status == 200
    assert isinstance(data, dict)
