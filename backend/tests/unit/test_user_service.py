"""Unit tests for UserService."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.core.user.service.user_service import UserService
from app.core.user.types import UserCreateDTO, UserDTO, UserUpdateDTO
from app.db.models.user import User

TEST_USER_EMAIL = "test@example.com"
TEST_USER_PASSWORD = "securepassword123"
TEST_USER_FULL_NAME = "Test User"
TEST_USER_ID = uuid4()


class TestUserServiceGet:
    @pytest.mark.asyncio
    async def test_get_by_id_found(
        self,
        user_service: UserService,
        mock_user_repository: MagicMock,
        sample_user_model: MagicMock,
    ) -> None:
        mock_user_repository.find_by_primary_key = AsyncMock(return_value=sample_user_model)
        result = await user_service.get_by_id(TEST_USER_ID)
        assert result is not None
        assert result.email == sample_user_model.email
        mock_user_repository.find_by_primary_key.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_by_id_not_found(
        self, user_service: UserService, mock_user_repository: MagicMock
    ) -> None:
        mock_user_repository.find_by_primary_key = AsyncMock(return_value=None)
        result = await user_service.get_by_id(TEST_USER_ID)
        assert result is None

    @pytest.mark.asyncio
    async def test_get_by_email_found(
        self,
        user_service: UserService,
        mock_user_repository: MagicMock,
        sample_user_model: MagicMock,
    ) -> None:
        mock_user_repository.find_by_email = AsyncMock(return_value=sample_user_model)
        result = await user_service.get_by_email(TEST_USER_EMAIL)
        assert result is not None
        assert result.email == TEST_USER_EMAIL

    @pytest.mark.asyncio
    async def test_get_by_email_not_found(
        self, user_service: UserService, mock_user_repository: MagicMock
    ) -> None:
        mock_user_repository.find_by_email = AsyncMock(return_value=None)
        result = await user_service.get_by_email(TEST_USER_EMAIL)
        assert result is None

    @pytest.mark.asyncio
    async def test_get_user_model_by_id(
        self,
        user_service: UserService,
        mock_user_repository: MagicMock,
        sample_user_model: MagicMock,
    ) -> None:
        mock_user_repository.find_by_primary_key = AsyncMock(return_value=sample_user_model)
        result = await user_service.get_user_model_by_id(TEST_USER_ID)
        assert result is not None
        assert hasattr(result, "hashed_password")

    @pytest.mark.asyncio
    async def test_get_user_model_by_email(
        self,
        user_service: UserService,
        mock_user_repository: MagicMock,
        sample_user_model: MagicMock,
    ) -> None:
        mock_user_repository.find_by_email = AsyncMock(return_value=sample_user_model)
        result = await user_service.get_user_model_by_email(TEST_USER_EMAIL)
        assert result is not None
        assert hasattr(result, "hashed_password")


class TestUserServiceCreate:
    @pytest.mark.asyncio
    async def test_create_user_success(
        self, user_service: UserService, mock_user_repository: MagicMock
    ) -> None:
        user_data = UserCreateDTO(
            email=TEST_USER_EMAIL,
            username="newuser",
            full_name=TEST_USER_FULL_NAME,
            password=TEST_USER_PASSWORD,
        )
        created_user = UserDTO(
            id=TEST_USER_ID,
            email=user_data.email,
            username=user_data.username,
            full_name=user_data.full_name,
            is_active=True,
            is_superuser=False,
            created_at=datetime.now(UTC),
        )
        mock_user_repository.create = AsyncMock(return_value=created_user)

        result = await user_service.create(user_data)

        assert result.email == TEST_USER_EMAIL
        assert result.username == "newuser"
        mock_user_repository.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_user_with_password_success(
        self, user_service: UserService, mock_user_repository: MagicMock
    ) -> None:
        hashed_password = "$2b$12$testhashedpassword"
        created_user = UserDTO(
            id=TEST_USER_ID,
            email=TEST_USER_EMAIL,
            full_name=TEST_USER_FULL_NAME,
            is_active=True,
            is_superuser=False,
            created_at=datetime.now(UTC),
        )
        mock_user_repository.insert = AsyncMock(return_value=created_user)

        result = await user_service.create_user_with_password(
            email=TEST_USER_EMAIL,
            hashed_password=hashed_password,
            full_name=TEST_USER_FULL_NAME,
        )

        assert result.email == TEST_USER_EMAIL
        mock_user_repository.insert.assert_called_once()


class TestUserServiceUpdate:
    @pytest.mark.asyncio
    async def test_update_user_success(
        self,
        user_service: UserService,
        mock_user_repository: MagicMock,
        sample_user_model: MagicMock,
    ) -> None:
        mock_user_repository.find_by_primary_key = AsyncMock(return_value=sample_user_model)
        updated_user = UserDTO(
            id=TEST_USER_ID,
            email="updated@example.com",
            username="updateduser",
            full_name=TEST_USER_FULL_NAME,
            is_active=True,
            is_superuser=False,
            created_at=datetime.now(UTC),
        )
        mock_user_repository.update = AsyncMock(return_value=updated_user)

        update_data = UserUpdateDTO(email="updated@example.com", username="updateduser")
        result = await user_service.update(TEST_USER_ID, update_data)

        assert result is not None
        assert result.email == "updated@example.com"

    @pytest.mark.asyncio
    async def test_update_user_not_found(
        self, user_service: UserService, mock_user_repository: MagicMock
    ) -> None:
        mock_user_repository.find_by_primary_key = AsyncMock(return_value=None)
        update_data = UserUpdateDTO(email="updated@example.com")
        result = await user_service.update(TEST_USER_ID, update_data)
        assert result is None

    @pytest.mark.asyncio
    async def test_update_user_partial(
        self,
        user_service: UserService,
        mock_user_repository: MagicMock,
        sample_user_model: MagicMock,
    ) -> None:
        mock_user_repository.find_by_primary_key = AsyncMock(return_value=sample_user_model)
        updated_user = UserDTO(
            id=TEST_USER_ID,
            email=sample_user_model.email,
            username="newusername",
            full_name=sample_user_model.full_name,
            is_active=True,
            is_superuser=False,
            created_at=datetime.now(UTC),
        )
        mock_user_repository.update = AsyncMock(return_value=updated_user)

        update_data = UserUpdateDTO(username="newusername")
        result = await user_service.update(TEST_USER_ID, update_data)

        assert result is not None
        assert result.username == "newusername"

    @pytest.mark.asyncio
    async def test_update_password_success(
        self,
        user_service: UserService,
        mock_user_repository: MagicMock,
        sample_user_model: MagicMock,
    ) -> None:
        mock_user_repository.find_by_primary_key = AsyncMock(return_value=sample_user_model)
        mock_user_repository.update = AsyncMock(return_value=sample_user_model)

        result = await user_service.update_password(TEST_USER_ID, "$2b$12$newpasswordhash")
        assert result is True

    @pytest.mark.asyncio
    async def test_update_password_user_not_found(
        self, user_service: UserService, mock_user_repository: MagicMock
    ) -> None:
        mock_user_repository.find_by_primary_key = AsyncMock(return_value=None)
        result = await user_service.update_password(TEST_USER_ID, "$2b$12$newpasswordhash")
        assert result is False


class TestUserServiceDelete:
    @pytest.mark.asyncio
    async def test_delete_user_success(
        self,
        user_service: UserService,
        mock_user_repository: MagicMock,
        sample_user_model: MagicMock,
    ) -> None:
        mock_user_repository.find_by_primary_key = AsyncMock(return_value=sample_user_model)
        mock_user_repository.delete = AsyncMock()

        result = await user_service.delete(TEST_USER_ID)

        assert result is True
        mock_user_repository.delete.assert_called_once_with(sample_user_model.id)

    @pytest.mark.asyncio
    async def test_delete_user_not_found(
        self, user_service: UserService, mock_user_repository: MagicMock
    ) -> None:
        mock_user_repository.find_by_primary_key = AsyncMock(return_value=None)
        result = await user_service.delete(TEST_USER_ID)
        assert result is False
        mock_user_repository.delete.assert_not_called()


class TestUserServiceList:
    @pytest.mark.asyncio
    async def test_list_users_empty(
        self, user_service: UserService, mock_user_repository: MagicMock
    ) -> None:
        mock_user_repository.find_all = AsyncMock(return_value=[])
        result = await user_service.list_users()
        assert result == []

    @pytest.mark.asyncio
    async def test_list_users_with_results(
        self,
        user_service: UserService,
        mock_user_repository: MagicMock,
        sample_user_model: MagicMock,
    ) -> None:
        users = [
            sample_user_model,
            User(
                id=uuid4(),
                email="user2@example.com",
                username="user2",
                full_name="User Two",
                hashed_password="$2b$12$hash2",
                is_active=True,
                is_superuser=False,
                created_at=datetime.now(UTC),
            ),
        ]
        mock_user_repository.find_all = AsyncMock(return_value=users)

        result = await user_service.list_users()
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_list_users_with_pagination(
        self, user_service: UserService, mock_user_repository: MagicMock
    ) -> None:
        mock_user_repository.find_all = AsyncMock(return_value=[])
        await user_service.list_users(limit=10, offset=5)
        mock_user_repository.find_all.assert_called_once()
        call_kwargs = mock_user_repository.find_all.call_args[1]
        assert call_kwargs["limit"] == 10
        assert call_kwargs["offset"] == 5


class TestUserDTODisplayName:
    def test_display_name_full_name(self) -> None:
        user = UserDTO(
            id=TEST_USER_ID,
            email="test@example.com",
            username="testuser",
            full_name="Test User",
            created_at=datetime.now(UTC),
        )
        assert user.display_name == "Test User"

    def test_display_name_username(self) -> None:
        user = UserDTO(
            id=TEST_USER_ID,
            email="test@example.com",
            username="testuser",
            full_name=None,
            created_at=datetime.now(UTC),
        )
        assert user.display_name == "testuser"

    def test_display_name_email(self) -> None:
        user = UserDTO(
            id=TEST_USER_ID,
            email="test@example.com",
            username=None,
            full_name=None,
            created_at=datetime.now(UTC),
        )
        assert user.display_name == "test@example.com"
