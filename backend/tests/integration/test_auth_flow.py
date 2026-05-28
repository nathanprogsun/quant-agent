"""Integration tests for auth API flows."""
from __future__ import annotations

import pytest
from uuid import uuid4

from tests.integration.client import APITestClient


class TestAuthFlow:
    """Test authentication flow with real HTTP requests.

    Uses APITestClient for simplified API calls.
    Tests both authenticated and unauthenticated scenarios.
    """

    @pytest.mark.asyncio
    async def test_register_success(self, authed_api_client: APITestClient) -> None:
        """Registered user can access /me endpoint."""
        user = await authed_api_client.get("/api/v1/auth/me")
        assert user["email"]
        assert "id" in user

    @pytest.mark.asyncio
    async def test_me_unauthenticated_returns_401(
        self, noauthed_api_client: APITestClient
    ) -> None:
        """Unauthenticated access to /me returns 401."""
        status, data = await noauthed_api_client.get_raw("/api/v1/auth/me")
        assert status == 401

    @pytest.mark.asyncio
    async def test_login_success(self, noauthed_api_client: APITestClient) -> None:
        """Login with valid credentials succeeds."""
        # Register first
        register_data = {
            "email": f"logintest{uuid4()}@test.com",
            "password": "TestPassword123!",
            "full_name": "Login Test User",
        }
        await noauthed_api_client.post("/api/v1/auth/register", json=register_data)

        # Login
        login_data = {
            "email": register_data["email"],
            "password": register_data["password"],
        }
        status, _ = await noauthed_api_client.post_raw("/api/v1/auth/login", json=login_data)
        assert status == 200

        # Now can access protected endpoint
        user = await noauthed_api_client.get("/api/v1/auth/me")
        assert user["email"] == register_data["email"]

    @pytest.mark.asyncio
    async def test_login_wrong_password(self, noauthed_api_client: APITestClient) -> None:
        """Login with wrong password returns 401."""
        # Register first
        register_data = {
            "email": f"wrongpwd{uuid4()}@test.com",
            "password": "CorrectPassword123!",
            "full_name": "Wrong Pwd User",
        }
        await noauthed_api_client.post("/api/v1/auth/register", json=register_data)

        # Login with wrong password
        login_data = {
            "email": register_data["email"],
            "password": "WrongPassword123!",
        }
        status, data = await noauthed_api_client.get_raw("/api/v1/auth/login", json=login_data)
        assert status == 401

    @pytest.mark.asyncio
    async def test_login_nonexistent_user(self, noauthed_api_client: APITestClient) -> None:
        """Login with non-existent email returns 401."""
        login_data = {
            "email": f"nonexistent{uuid4()}@test.com",
            "password": "AnyPassword123!",
        }
        status, _ = await noauthed_api_client.get_raw("/api/v1/auth/login", json=login_data)
        assert status == 401

    @pytest.mark.asyncio
    async def test_signout(self, authed_api_client: APITestClient) -> None:
        """Signout clears session."""
        status, _ = await authed_api_client.get_raw("/api/v1/auth/signout")
        assert status == 200

    @pytest.mark.asyncio
    async def test_setup_status(self, noauthed_api_client: APITestClient) -> None:
        """Setup status endpoint is public."""
        status, data = await noauthed_api_client.get_raw("/api/v1/auth/setup-status")
        assert status == 200
        assert "needs_setup" in data
