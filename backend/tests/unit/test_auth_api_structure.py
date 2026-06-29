"""Unit tests for auth API structure (routes, models)."""

from __future__ import annotations

import pytest

from app.core.auth.types import AuthResponse, ChangePasswordRequest, LoginRequest, RegisterRequest
from app.web.api.auth.views import router


class TestAuthAPIStructure:
    def test_auth_router_exists(self) -> None:

        assert router is not None
        assert router.prefix == "/api/v1/auth"

    def test_auth_endpoints_registered(self) -> None:

        routes: set[str] = set()
        for route in router.routes:
            if hasattr(route, "path"):
                routes.add(route.path)

        expected_routes = {
            "/api/v1/auth/register",
            "/api/v1/auth/login",
            "/api/v1/auth/signout",
            "/api/v1/auth/change-password",
            "/api/v1/auth/me",
        }
        for expected_path in expected_routes:
            assert expected_path in routes, f"Missing route: {expected_path}"

    def test_login_request_model(self) -> None:

        valid = LoginRequest(email="test@example.com", password="password123")
        assert valid.email == "test@example.com"

        with pytest.raises(ValueError):
            LoginRequest(email="not-an-email", password="password")

    def test_register_request_model(self) -> None:

        valid = RegisterRequest(
            email="test@example.com", password="password123", full_name="Test User"
        )
        assert valid.email == "test@example.com"
        assert valid.full_name == "Test User"

        with pytest.raises(ValueError):
            RegisterRequest(email="test@example.com", password="password")  # type: ignore[call-arg]

        with pytest.raises(ValueError):
            RegisterRequest(email="test@example.com", full_name="Test User")  # type: ignore[call-arg]

    def test_change_password_request_model(self) -> None:

        valid = ChangePasswordRequest(old_password="oldpass", new_password="newpass")
        assert valid.old_password == "oldpass"
        assert valid.new_password == "newpass"

    def test_auth_response_model(self) -> None:

        response = AuthResponse(message="Success", user_id="123")
        assert response.message == "Success"
        assert response.user_id == "123"

        response2 = AuthResponse(message="Error")
        assert response2.user_id is None
