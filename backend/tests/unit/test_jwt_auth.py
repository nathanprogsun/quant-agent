"""JWT authentication unit tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from pydantic import SecretStr

from app.core.auth.service.auth_service import AuthService
from app.core.auth.types import TokenClaims


@pytest.fixture
def jwt_settings() -> MagicMock:
    mock = MagicMock()
    mock.jwt_secret_key = SecretStr("test-secret-key-for-jwt")
    mock.jwt_algorithm = "HS256"
    mock.jwt_expire_minutes = 60
    mock.jwt_issuer = "test-issuer"
    mock.jwt_audience = "test-audience"
    return mock


@pytest.fixture
def jwt_auth_service() -> AuthService:


    mock_user_service = AsyncMock()
    return AuthService(user_service=mock_user_service)


class TestCreateAccessToken:
    """Tests for JWT token creation."""

    def test_creates_valid_token(self, jwt_auth_service: AuthService, jwt_settings: MagicMock) -> None:
        user_id = uuid4()
        with patch("app.core.auth.service.auth_service.get_settings", return_value=jwt_settings):
            token = jwt_auth_service.create_access_token(
                data=TokenClaims(sub=user_id, email="test@example.com")
            )
        assert isinstance(token, str)
        assert len(token) > 0

    def test_decodes_token_with_correct_claims(self, jwt_auth_service: AuthService, jwt_settings: MagicMock) -> None:
        user_id = uuid4()
        email = "test@example.com"
        with patch("app.core.auth.service.auth_service.get_settings", return_value=jwt_settings):
            token = jwt_auth_service.create_access_token(
                data=TokenClaims(sub=user_id, email=email)
            )
            payload = jwt_auth_service.decode_token(token)

        assert payload is not None
        assert payload.sub == user_id
        assert payload.email == email

    def test_sets_exp_claim(self, jwt_auth_service: AuthService, jwt_settings: MagicMock) -> None:
        before = datetime.now(UTC)
        with patch("app.core.auth.service.auth_service.get_settings", return_value=jwt_settings):
            token = jwt_auth_service.create_access_token(data=TokenClaims(sub=uuid4(), email="a@b.com"))
            payload = jwt_auth_service.decode_token(token)

        assert payload is not None
        exp_value = payload.model_extra["exp"] if payload.model_extra and "exp" in payload.model_extra else None
        assert exp_value is not None
        exp = datetime.fromtimestamp(exp_value, tz=UTC)
        expected_min = before + timedelta(minutes=59)
        expected_max = before + timedelta(minutes=61)
        assert expected_min <= exp <= expected_max

    def test_uses_secret_value_not_secret_str(self, jwt_auth_service: AuthService, jwt_settings: MagicMock) -> None:
        """Verify .get_secret_value() is called, not raw SecretStr."""
        with patch("app.core.auth.service.auth_service.get_settings", return_value=jwt_settings):
            token = jwt_auth_service.create_access_token(data=TokenClaims(sub=uuid4(), email="a@b.com"))
            # Should decode successfully (proves secret value was used)
            payload = jwt_auth_service.decode_token(token)
        assert payload is not None


class TestDecodeToken:
    """Tests for JWT token decoding."""

    def test_returns_none_for_expired_token(self, jwt_auth_service: AuthService, jwt_settings: MagicMock) -> None:
        jwt_settings.jwt_expire_minutes = -1  # Already expired
        with patch("app.core.auth.service.auth_service.get_settings", return_value=jwt_settings):
            token = jwt_auth_service.create_access_token(data=TokenClaims(sub=uuid4(), email="a@b.com"))
            payload = jwt_auth_service.decode_token(token)
        assert payload is None

    def test_returns_none_for_invalid_signature(self, jwt_auth_service: AuthService, jwt_settings: MagicMock) -> None:
        with patch("app.core.auth.service.auth_service.get_settings", return_value=jwt_settings):
            token = jwt_auth_service.create_access_token(data=TokenClaims(sub=uuid4(), email="a@b.com"))

        # Decode with different secret
        different_settings = MagicMock()
        different_settings.jwt_secret_key = SecretStr("different-secret")
        different_settings.jwt_algorithm = "HS256"
        different_settings.jwt_issuer = "test-issuer"
        different_settings.jwt_audience = "test-audience"
        with patch("app.core.auth.service.auth_service.get_settings", return_value=different_settings):
            payload = jwt_auth_service.decode_token(token)
        assert payload is None

    def test_returns_none_for_malformed_token(self, jwt_auth_service: AuthService, jwt_settings: MagicMock) -> None:
        with patch("app.core.auth.service.auth_service.get_settings", return_value=jwt_settings):
            payload = jwt_auth_service.decode_token("not.a.valid.token")
        assert payload is None

    def test_returns_none_for_empty_string(self, jwt_auth_service: AuthService, jwt_settings: MagicMock) -> None:
        with patch("app.core.auth.service.auth_service.get_settings", return_value=jwt_settings):
            payload = jwt_auth_service.decode_token("")
        assert payload is None

    def test_converts_sub_back_to_uuid(self, jwt_auth_service: AuthService, jwt_settings: MagicMock) -> None:
        user_id = uuid4()
        with patch("app.core.auth.service.auth_service.get_settings", return_value=jwt_settings):
            token = jwt_auth_service.create_access_token(data=TokenClaims(sub=user_id, email="a@b.com"))
            payload = jwt_auth_service.decode_token(token)

        assert payload is not None
        assert payload.sub == user_id
