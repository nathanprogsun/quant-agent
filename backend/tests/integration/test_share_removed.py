"""Verify share API has been removed (404)."""

import pytest

from tests.integration.client import APITestClient


@pytest.mark.asyncio
async def test_share_routes_return_404(authed_api_client: APITestClient) -> None:
    """Share routes should return 404 after removal (even when authenticated)."""
    status, _ = await authed_api_client.get_raw("/api/v1/share/nonexistent-id")
    assert status == 404
