"""Integration tests for chat API."""
from __future__ import annotations

from uuid import uuid4

import pytest

from tests.integration.client import APITestClient


class TestChatAPI:
    """Test chat endpoint authentication.

    Tests both authenticated and unauthenticated scenarios.
    """

    @pytest.mark.asyncio
    async def test_stream_run_requires_auth(
        self, noauthed_api_client: APITestClient
    ) -> None:
        """Unauthenticated access to stream_run returns 401."""
        thread_id = uuid4()
        status, _ = await noauthed_api_client.post_raw(
            f"/api/v1/chat/{thread_id}/runs/stream",
            json={
                "input": {"messages": []},
                "config": {},
                "context": {},
            },
        )
        assert status == 401

    @pytest.mark.asyncio
    async def test_cancel_run_requires_auth(
        self, noauthed_api_client: APITestClient
    ) -> None:
        """Unauthenticated access to cancel_run returns 401."""
        thread_id = uuid4()
        run_id = uuid4()
        status, _ = await noauthed_api_client.post_raw(
            f"/api/v1/chat/{thread_id}/runs/{run_id}/cancel",
        )
        assert status == 401

    @pytest.mark.asyncio
    async def test_stream_run_authenticated_without_thread(
        self, authed_api_client: APITestClient
    ) -> None:
        """Authenticated user with non-existent thread gets 404."""
        thread_id = uuid4()
        status, _ = await authed_api_client.post_raw(
            f"/api/v1/chat/{thread_id}/runs/stream",
            json={
                "input": {"messages": []},
                "config": {},
                "context": {},
            },
        )
        # 404 means auth passed but thread not found
        assert status == 404

    @pytest.mark.asyncio
    async def test_cancel_run_authenticated_without_run(
        self, authed_api_client: APITestClient
    ) -> None:
        """Authenticated user with non-existent run gets 404."""
        thread_id = uuid4()
        run_id = uuid4()
        status, _ = await authed_api_client.post_raw(
            f"/api/v1/chat/{thread_id}/runs/{run_id}/cancel",
        )
        # 404 means auth passed but run not found
        assert status == 404
