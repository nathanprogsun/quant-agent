"""Integration tests for LangGraph-compatible history and state endpoints."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from langchain_core.messages import HumanMessage

from app.app_context.app_context import AppContext
from app.web.api.thread.checkpoint_state import new_checkpoint, thread_config
from app.web.application import get_app
from tests.integration.client import APITestClient


@pytest.mark.integration
class TestThreadStateAPI:
    """POST /history and GET/POST /state with ownership checks."""

    @pytest.mark.asyncio
    async def test_post_history_returns_thread_states(
        self,
        authed_api_client: APITestClient,
        test_app_context: AppContext,
    ) -> None:
        thread = await authed_api_client.post(
            "/api/v1/threads",
            json={"model_name": "gpt-4"},
        )
        thread_id = UUID(thread["id"])

        checkpointer = test_app_context.checkpointer
        assert checkpointer is not None

        config = thread_config(thread_id)
        checkpoint = new_checkpoint(
            {"messages": [HumanMessage(content="hello", id="m1")]}
        )
        await checkpointer.aput(config, checkpoint, {}, {})

        response = await authed_api_client._client.post(
            f"/api/v1/threads/{thread_id}/history",
            json={"limit": 10},
        )

        assert response.status_code == 200
        body = response.json()
        assert isinstance(body, list)
        assert len(body) >= 1
        assert "values" in body[0]
        assert body[0]["values"]["messages"][0]["type"] == "human"
        assert body[0]["values"]["messages"][0]["data"]["content"] == "hello"

    @pytest.mark.asyncio
    async def test_get_state_returns_latest_values(
        self,
        authed_api_client: APITestClient,
        test_app_context: AppContext,
    ) -> None:
        thread = await authed_api_client.post(
            "/api/v1/threads",
            json={"model_name": "gpt-4"},
        )
        thread_id = UUID(thread["id"])

        checkpointer = test_app_context.checkpointer
        assert checkpointer is not None

        config = thread_config(thread_id)
        checkpoint = new_checkpoint(
            {"messages": [HumanMessage(content="state-check", id="m2")]}
        )
        await checkpointer.aput(config, checkpoint, {}, {})

        body = await authed_api_client.get(f"/api/v1/threads/{thread_id}/state")

        assert body["values"]["messages"][0]["type"] == "human"
        assert body["values"]["messages"][0]["data"]["content"] == "state-check"
        assert body["checkpoint"]["thread_id"] == str(thread_id)

    @pytest.mark.asyncio
    async def test_get_state_empty_for_new_thread(
        self,
        authed_api_client: APITestClient,
    ) -> None:
        thread = await authed_api_client.post(
            "/api/v1/threads",
            json={"model_name": "gpt-4"},
        )

        body = await authed_api_client.get(f"/api/v1/threads/{thread['id']}/state")

        assert body["values"] == {}
        assert body["checkpoint"]["thread_id"] == thread["id"]

    @pytest.mark.asyncio
    async def test_post_state_updates_values(
        self,
        authed_api_client: APITestClient,
    ) -> None:
        thread = await authed_api_client.post(
            "/api/v1/threads",
            json={"model_name": "gpt-4"},
        )
        thread_id = thread["id"]

        updated = await authed_api_client.post(
            f"/api/v1/threads/{thread_id}/state",
            json={
                "values": {
                    "messages": [
                        {
                            "type": "human",
                            "content": "persisted",
                            "id": "m3",
                        }
                    ]
                }
            },
        )

        assert updated["values"]["messages"][0]["type"] == "human"

        loaded = await authed_api_client.get(f"/api/v1/threads/{thread_id}/state")
        assert loaded["values"]["messages"][0]["type"] == "human"

    @pytest.mark.asyncio
    async def test_history_requires_thread_ownership(
        self,
        test_app_context: AppContext,
    ) -> None:
        app = get_app()
        app.state.app_context = test_app_context
        transport = ASGITransport(app=app)

        async with (
            AsyncClient(transport=transport, base_url="http://test") as client_a,
            AsyncClient(transport=transport, base_url="http://test") as client_b,
        ):
            user_a = APITestClient(client_a)
            await user_a.post(
                "/api/v1/auth/register",
                json={
                    "email": f"{uuid4()}@test.com",
                    "password": "TestPassword123!",
                    "full_name": "User A",
                },
            )
            user_b = APITestClient(client_b)
            await user_b.post(
                "/api/v1/auth/register",
                json={
                    "email": f"{uuid4()}@test.com",
                    "password": "TestPassword123!",
                    "full_name": "User B",
                },
            )

            thread = await user_a.post("/api/v1/threads", json={"model_name": "gpt-4"})
            status, _ = await user_b.post_raw(
                f"/api/v1/threads/{thread['id']}/history",
                json={"limit": 1},
            )

        assert status == 404
