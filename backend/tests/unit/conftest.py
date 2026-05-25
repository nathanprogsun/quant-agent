"""Unit test fixtures."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
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
TEST_USER_ID = str(uuid4())


@pytest.fixture
def sample_user_data() -> dict[str, Any]:
    return {
        "email": TEST_USER_EMAIL,
        "username": "testuser",
        "full_name": TEST_USER_FULL_NAME,
        "password": TEST_USER_PASSWORD,
    }


@pytest.fixture
def sample_user_dto() -> UserDTO:
    return UserDTO(
        id=TEST_USER_ID,
        email=TEST_USER_EMAIL,
        username="testuser",
        full_name=TEST_USER_FULL_NAME,
        is_active=True,
        is_superuser=False,
        created_at=datetime.now(UTC),
    )


@pytest.fixture
def sample_user_model() -> User:
    return User(
        id=TEST_USER_ID,
        email=TEST_USER_EMAIL,
        username="testuser",
        full_name=TEST_USER_FULL_NAME,
        hashed_password="$2b$12$test_hash",
        is_active=True,
        is_superuser=False,
        created_at=datetime.now(UTC),
    )


@pytest.fixture
def mock_user_repository() -> MagicMock:
    mock = MagicMock()
    mock.find_by_email = AsyncMock(return_value=None)
    mock.find_by_primary_key = AsyncMock(return_value=None)
    mock.create = AsyncMock()
    mock.update = AsyncMock()
    mock.insert = AsyncMock()
    mock.delete = AsyncMock()
    mock.find_all = AsyncMock(return_value=[])
    return mock


@pytest.fixture
def mock_user_service() -> AsyncMock:
    mock = AsyncMock(spec=UserService)
    mock.get_by_id = AsyncMock(return_value=None)
    mock.get_by_email = AsyncMock(return_value=None)
    mock.get_user_model_by_id = AsyncMock(return_value=None)
    mock.get_user_model_by_email = AsyncMock(return_value=None)
    mock.create = AsyncMock()
    mock.create_user_with_password = AsyncMock()
    mock.update = AsyncMock()
    mock.delete = AsyncMock()
    mock.list_users = AsyncMock(return_value=[])
    mock.update_password = AsyncMock(return_value=True)
    return mock


@pytest.fixture
def auth_service(mock_user_service: AsyncMock) -> AuthService:
    return AuthService(user_service=mock_user_service)


@pytest.fixture
def user_service(mock_user_repository: MagicMock) -> UserService:
    return UserService(user_repository=mock_user_repository)


@pytest.fixture
def mock_settings() -> MagicMock:
    mock = MagicMock()
    mock.jwt_secret_key = "test-secret-key-for-testing"
    mock.jwt_algorithm = "HS256"
    mock.jwt_expire_minutes = 60 * 24 * 7
    return mock


@pytest.fixture
def valid_token(auth_service: AuthService, mock_settings: MagicMock) -> str:
    with patch("app.core.auth.service.auth_service.get_settings", return_value=mock_settings):
        return auth_service.create_access_token(
            data={"sub": TEST_USER_ID, "email": TEST_USER_EMAIL}
        )
