"""Integration tests for thread API."""
from __future__ import annotations

from uuid import uuid4

import pytest

from tests.integration.client import APITestClient


class TestThreadAPI:
    """Test thread CRUD operations.

    Tests both authenticated and unauthenticated access.
    """

    @pytest.mark.asyncio
    async def test_create_thread_authenticated(
        self, authed_api_client: APITestClient
    ) -> None:
        """Authenticated user can create a thread."""
        thread_data = {
            "model_name": "gpt-4",
        }
        thread = await authed_api_client.post("/api/v1/threads", json=thread_data)
        assert thread["id"]
        assert thread["model_name"] == thread_data["model_name"]

    @pytest.mark.asyncio
    async def test_create_thread_unauthenticated(
        self, noauthed_api_client: APITestClient
    ) -> None:
        """Unauthenticated user cannot create thread."""
        thread_data = {
            "model_name": "gpt-4",
        }
        status, _ = await noauthed_api_client.post_raw("/api/v1/threads", json=thread_data)
        assert status == 401

    @pytest.mark.asyncio
    async def test_list_threads_authenticated(
        self, authed_api_client: APITestClient
    ) -> None:
        """Authenticated user can list their threads."""
        # Create a thread first
        thread_data = {"model_name": "gpt-4"}
        await authed_api_client.post("/api/v1/threads", json=thread_data)

        # List threads
        response = await authed_api_client.get("/api/v1/threads")
        assert "threads" in response
        assert isinstance(response["threads"], list)
        assert len(response["threads"]) >= 1

    @pytest.mark.asyncio
    async def test_list_threads_unauthenticated(
        self, noauthed_api_client: APITestClient
    ) -> None:
        """Unauthenticated user cannot list threads."""
        status, _ = await noauthed_api_client.get_raw("/api/v1/threads")
        assert status == 401

    @pytest.mark.asyncio
    async def test_get_thread_authenticated(
        self, authed_api_client: APITestClient
    ) -> None:
        """Authenticated user can get a specific thread."""
        # Create thread
        thread_data = {"model_name": "gpt-4"}
        created = await authed_api_client.post("/api/v1/threads", json=thread_data)

        # Get thread
        thread = await authed_api_client.get(f"/api/v1/threads/{created['id']}")
        assert thread["id"] == created["id"]
        assert thread["model_name"] == thread_data["model_name"]

    @pytest.mark.asyncio
    async def test_get_thread_unauthenticated(
        self, noauthed_api_client: APITestClient
    ) -> None:
        """Unauthenticated user cannot get thread."""
        fake_id = str(uuid4())
        status, _ = await noauthed_api_client.get_raw(f"/api/v1/threads/{fake_id}")
        assert status == 401

    @pytest.mark.asyncio
    async def test_update_thread_title_authenticated(
        self, authed_api_client: APITestClient
    ) -> None:
        """Authenticated user can update thread title."""
        # Create thread
        thread_data = {"model_name": "gpt-4"}
        created = await authed_api_client.post("/api/v1/threads", json=thread_data)

        # Update title
        new_title = f"Updated Title {uuid4()}"
        updated = await authed_api_client.patch(
            f"/api/v1/threads/{created['id']}",
            json={"title": new_title}
        )
        assert updated["id"] == created["id"]
        assert updated["title"] == new_title

    @pytest.mark.asyncio
    async def test_update_thread_unauthenticated(
        self, noauthed_api_client: APITestClient
    ) -> None:
        """Unauthenticated user cannot update thread."""
        fake_id = str(uuid4())
        status, _ = await noauthed_api_client.patch_raw(
            f"/api/v1/threads/{fake_id}",
            json={"title": "New Title"}
        )
        assert status == 401

    @pytest.mark.asyncio
    async def test_delete_thread_authenticated(
        self, authed_api_client: APITestClient
    ) -> None:
        """Authenticated user can delete a thread."""
        # Create thread
        thread_data = {"model_name": "gpt-4"}
        created = await authed_api_client.post("/api/v1/threads", json=thread_data)

        # Delete thread
        status, _ = await authed_api_client.delete_raw(f"/api/v1/threads/{created['id']}")
        assert status == 204

    @pytest.mark.asyncio
    async def test_delete_thread_unauthenticated(
        self, noauthed_api_client: APITestClient
    ) -> None:
        """Unauthenticated user cannot delete thread."""
        fake_id = str(uuid4())
        status, _ = await noauthed_api_client.delete_raw(f"/api/v1/threads/{fake_id}")
        assert status == 401

    @pytest.mark.asyncio
    async def test_delete_nonexistent_thread(
        self, authed_api_client: APITestClient
    ) -> None:
        """Deleting non-existent thread returns 404."""
        fake_id = str(uuid4())
        status, _ = await authed_api_client.delete_raw(f"/api/v1/threads/{fake_id}")
        assert status == 404
