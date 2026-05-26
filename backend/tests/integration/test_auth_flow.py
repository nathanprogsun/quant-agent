"""Integration tests for auth service flows."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.core.auth.service.auth_service import AuthService
from app.core.user.service.user_service import UserService
from app.core.user.types import UserDTO
from app.db.models.user import User

TEST_USER_EMAIL = "test@example.com"
TEST_USER_PASSWORD = "securepassword123"
TEST_USER_FULL_NAME = "Test User"
TEST_USER_ID = uuid4()


class TestAuthServiceAPIIntegration:
    def test_create_and_validate_token(self, mock_settings: MagicMock) -> None:
        mock_user_service = AsyncMock()
        auth_service = AuthService(user_service=mock_user_service)

        with patch("app.core.auth.service.auth_service.get_settings", return_value=mock_settings):
            token = auth_service.create_access_token(
                data={"sub": TEST_USER_ID, "email": TEST_USER_EMAIL}
            )
            assert isinstance(token, str)

            payload = auth_service.decode_token(token)
            assert payload is not None
            assert payload["sub"] == TEST_USER_ID
            assert payload["email"] == TEST_USER_EMAIL

    def test_csrf_token_in_response_flow(self) -> None:
        mock_user_service = AsyncMock()
        auth_service = AuthService(user_service=mock_user_service)

        csrf_token = auth_service.create_csrf_token()
        assert len(csrf_token) == 36
        assert "-" in csrf_token

    @pytest.mark.asyncio
    async def test_password_hashing_in_registration_flow(self, mock_settings: MagicMock) -> None:
        mock_user_service = AsyncMock(spec=UserService)
        mock_user_service.create_user_with_password = AsyncMock(
            return_value=UserDTO(
                id=TEST_USER_ID,
                email=TEST_USER_EMAIL,
                full_name=TEST_USER_FULL_NAME,
                created_at=datetime.now(UTC),
            )
        )

        auth_service = AuthService(user_service=mock_user_service)

        await auth_service.register_user(
            email=TEST_USER_EMAIL,
            password=TEST_USER_PASSWORD,
            full_name=TEST_USER_FULL_NAME,
        )

        mock_user_service.create_user_with_password.assert_called_once()
        call_args = mock_user_service.create_user_with_password.call_args[0]

        hashed_password = call_args[1]
        assert hashed_password != TEST_USER_PASSWORD
        assert hashed_password.startswith("$2b$")

    @pytest.mark.asyncio
    async def test_login_authentication_flow(self, mock_settings: MagicMock) -> None:
        mock_user_service = AsyncMock()
        auth_service = AuthService(user_service=mock_user_service)
        hashed_password = auth_service.get_password_hash(TEST_USER_PASSWORD)

        user_model = User(
            id=TEST_USER_ID,
            email=TEST_USER_EMAIL,
            username="testuser",
            full_name=TEST_USER_FULL_NAME,
            hashed_password=hashed_password,
            is_active=True,
            is_superuser=False,
            created_at=datetime.now(UTC),
        )
        mock_user_service.get_user_model_by_email = AsyncMock(return_value=user_model)

        result = await auth_service.authenticate_user(TEST_USER_EMAIL, TEST_USER_PASSWORD)

        assert result is not None
        assert result.email == TEST_USER_EMAIL

    @pytest.mark.asyncio
    async def test_login_failure_with_wrong_password(self, mock_settings: MagicMock) -> None:
        mock_user_service = AsyncMock()
        auth_service = AuthService(user_service=mock_user_service)
        hashed_password = auth_service.get_password_hash(TEST_USER_PASSWORD)

        user_model = User(
            id=TEST_USER_ID,
            email=TEST_USER_EMAIL,
            username="testuser",
            full_name=TEST_USER_FULL_NAME,
            hashed_password=hashed_password,
            is_active=True,
            is_superuser=False,
            created_at=datetime.now(UTC),
        )
        mock_user_service.get_user_model_by_email = AsyncMock(return_value=user_model)

        result = await auth_service.authenticate_user(TEST_USER_EMAIL, "wrong_password")
        assert result is None

    @pytest.mark.asyncio
    async def test_login_failure_user_not_found(self) -> None:
        mock_user_service = AsyncMock()
        mock_user_service.get_user_model_by_email = AsyncMock(return_value=None)
        auth_service = AuthService(user_service=mock_user_service)

        result = await auth_service.authenticate_user("nonexistent@example.com", "password")
        assert result is None
