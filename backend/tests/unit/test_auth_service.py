"""Unit tests for AuthService."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.common.exception import ResourceNotFoundError
from app.common.exception.exception import UnauthorizedError
from app.core.auth.service.auth_service import AuthService
from app.core.auth.types import TokenClaims
from app.core.user.types import UserDTO

TEST_USER_EMAIL = "test@example.com"
TEST_USER_PASSWORD = "securepassword123"
TEST_USER_FULL_NAME = "Test User"
TEST_USER_ID = uuid4()


class TestAuthServicePassword:
    def test_verify_password_correct(self, auth_service: AuthService) -> None:
        hashed = auth_service.get_password_hash(TEST_USER_PASSWORD)
        result = auth_service.verify_password(TEST_USER_PASSWORD, hashed)
        assert result is True

    def test_verify_password_incorrect(self, auth_service: AuthService) -> None:
        hashed = auth_service.get_password_hash(TEST_USER_PASSWORD)
        result = auth_service.verify_password("wrongpassword", hashed)
        assert result is False

    def test_get_password_hash_different_each_time(self, auth_service: AuthService) -> None:
        hash1 = auth_service.get_password_hash(TEST_USER_PASSWORD)
        hash2 = auth_service.get_password_hash(TEST_USER_PASSWORD)
        assert hash1 != hash2
        assert auth_service.verify_password(TEST_USER_PASSWORD, hash1)
        assert auth_service.verify_password(TEST_USER_PASSWORD, hash2)


class TestAuthServiceToken:
    def test_create_access_token(self, auth_service: AuthService, mock_settings: MagicMock) -> None:
        with patch("app.core.auth.service.auth_service.get_settings", return_value=mock_settings):
            token = auth_service.create_access_token(
                data=TokenClaims(sub=TEST_USER_ID, email=TEST_USER_EMAIL)
            )
            assert isinstance(token, str)
            assert len(token) > 0

    def test_create_access_token_with_custom_expiry(
        self, auth_service: AuthService, mock_settings: MagicMock
    ) -> None:
        with patch("app.core.auth.service.auth_service.get_settings", return_value=mock_settings):
            token = auth_service.create_access_token(
                data=TokenClaims(sub=TEST_USER_ID, email=TEST_USER_EMAIL),
                expires_delta=timedelta(hours=1),
            )
            assert isinstance(token, str)
            assert len(token) > 0

    def test_decode_token_valid(self, auth_service: AuthService, mock_settings: MagicMock) -> None:
        with patch("app.core.auth.service.auth_service.get_settings", return_value=mock_settings):
            token = auth_service.create_access_token(
                data=TokenClaims(sub=TEST_USER_ID, email=TEST_USER_EMAIL)
            )
            payload = auth_service.decode_token(token)
            assert payload is not None
            assert payload.sub == TEST_USER_ID
            assert payload.email == TEST_USER_EMAIL

    def test_decode_token_invalid(
        self, auth_service: AuthService, mock_settings: MagicMock
    ) -> None:
        with patch("app.core.auth.service.auth_service.get_settings", return_value=mock_settings):
            payload = auth_service.decode_token("invalid.token.here")
            assert payload is None

    def test_decode_token_tampered(
        self, auth_service: AuthService, mock_settings: MagicMock
    ) -> None:
        with patch("app.core.auth.service.auth_service.get_settings", return_value=mock_settings):
            token = auth_service.create_access_token(
                data=TokenClaims(sub=TEST_USER_ID, email=TEST_USER_EMAIL)
            )
            tampered_token = token[:-5] + "xxxxx"
            payload = auth_service.decode_token(tampered_token)
            assert payload is None


class TestAuthServiceAuthenticateUser:
    @pytest.mark.asyncio
    async def test_authenticate_user_success(
        self,
        auth_service: AuthService,
        mock_user_service: AsyncMock,
        sample_user_model: MagicMock,
    ) -> None:
        hashed_password = auth_service.get_password_hash(TEST_USER_PASSWORD)
        user_model = sample_user_model
        user_model.hashed_password = hashed_password
        user_model.email = TEST_USER_EMAIL
        mock_user_service.get_user_model_by_email = AsyncMock(return_value=user_model)

        result = await auth_service.authenticate_user(TEST_USER_EMAIL, TEST_USER_PASSWORD)

        assert result is not None
        assert result.email == TEST_USER_EMAIL
        mock_user_service.get_user_model_by_email.assert_called_once_with(TEST_USER_EMAIL)

    @pytest.mark.asyncio
    async def test_authenticate_user_not_found(
        self, auth_service: AuthService, mock_user_service: AsyncMock
    ) -> None:
        mock_user_service.get_user_model_by_email = AsyncMock(return_value=None)
        with pytest.raises(UnauthorizedError):
            await auth_service.authenticate_user(TEST_USER_EMAIL, TEST_USER_PASSWORD)

    @pytest.mark.asyncio
    async def test_authenticate_user_wrong_password(
        self,
        auth_service: AuthService,
        mock_user_service: AsyncMock,
        sample_user_model: MagicMock,
    ) -> None:
        hashed_password = auth_service.get_password_hash("correct_password")
        user_model = sample_user_model
        user_model.hashed_password = hashed_password
        user_model.email = TEST_USER_EMAIL
        mock_user_service.get_user_model_by_email = AsyncMock(return_value=user_model)

        with pytest.raises(UnauthorizedError):
            await auth_service.authenticate_user(TEST_USER_EMAIL, "wrong_password")


class TestAuthServiceRegisterUser:
    @pytest.mark.asyncio
    async def test_register_user_success(
        self,
        auth_service: AuthService,
        mock_user_service: AsyncMock,
        sample_user_dto: UserDTO,
    ) -> None:
        mock_user_service.create_user_with_password = AsyncMock(return_value=sample_user_dto)

        result = await auth_service.register_user(
            TEST_USER_EMAIL, TEST_USER_PASSWORD, TEST_USER_FULL_NAME
        )

        assert result == sample_user_dto
        mock_user_service.create_user_with_password.assert_called_once()
        call_args = mock_user_service.create_user_with_password.call_args
        dto_arg = call_args[0][0]
        assert dto_arg.email == TEST_USER_EMAIL
        assert dto_arg.full_name == TEST_USER_FULL_NAME
        assert dto_arg.hashed_password != TEST_USER_PASSWORD
        assert dto_arg.hashed_password.startswith("$2b$")


class TestAuthServiceChangePassword:
    @pytest.mark.asyncio
    async def test_change_password_success(
        self,
        auth_service: AuthService,
        mock_user_service: AsyncMock,
        sample_user_model: MagicMock,
    ) -> None:
        old_password = "old_password_123"
        new_password = "new_password_456"
        hashed_old = auth_service.get_password_hash(old_password)
        user_model = sample_user_model
        user_model.hashed_password = hashed_old

        mock_user_service.get_user_model_by_id = AsyncMock(return_value=user_model)
        mock_user_service.update_password = AsyncMock(return_value=True)

        await auth_service.change_password(TEST_USER_ID, old_password, new_password)

        mock_user_service.update_password.assert_called_once()

    @pytest.mark.asyncio
    async def test_change_password_user_not_found(
        self, auth_service: AuthService, mock_user_service: AsyncMock
    ) -> None:
        mock_user_service.get_user_model_by_id = AsyncMock(return_value=None)
        with pytest.raises(ResourceNotFoundError):
            await auth_service.change_password(TEST_USER_ID, "old_password", "new_password")

    @pytest.mark.asyncio
    async def test_change_password_wrong_old_password(
        self,
        auth_service: AuthService,
        mock_user_service: AsyncMock,
        sample_user_model: MagicMock,
    ) -> None:
        correct_password = "correct_password"
        wrong_password = "wrong_password"
        hashed_correct = auth_service.get_password_hash(correct_password)
        user_model = sample_user_model
        user_model.hashed_password = hashed_correct

        mock_user_service.get_user_model_by_id = AsyncMock(return_value=user_model)

        with pytest.raises(UnauthorizedError):
            await auth_service.change_password(TEST_USER_ID, wrong_password, "new_password")

        mock_user_service.update_password.assert_not_called()
