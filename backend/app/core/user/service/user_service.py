"""User service."""

from uuid import UUID, uuid4

from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.exception.exception import ResourceNotFoundError
from app.core.user.types import UserCreateDTO, UserCreateWithHashDTO, UserDTO, UserUpdateDTO
from app.db.dao.user_repository import UserRepository
from app.db.models.user import User
from app.util.time import zoned_utc_now

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class UserService:
    """Service for user operations.

    Receives a per-request AsyncSession. Repositories are constructed
    on-demand from that session. This service flushes but never commits;
    the FastAPI dependency commits at request end.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, user_id: UUID) -> UserDTO:
        """Get user by ID."""
        result = await UserRepository(self._session).find_by_id(user_id)
        if not result:
            raise ResourceNotFoundError(f"User with ID {user_id} not found")
        return UserDTO.model_validate(result)

    async def get_by_email(self, email: str) -> UserDTO | None:
        """Get user by email."""
        result = await UserRepository(self._session).find_by_email(email)
        return UserDTO.model_validate(result) if result else None

    async def get_user_model_by_id(self, user_id: UUID) -> User | None:
        """Get raw User model by ID (includes hashed_password)."""
        return await UserRepository(self._session).find_by_id(user_id)

    async def get_user_model_by_email(self, email: str) -> User | None:
        """Get raw User model by email (includes hashed_password)."""
        return await UserRepository(self._session).find_by_email(email)

    async def create(self, data: UserCreateDTO) -> UserDTO:
        """Create a new user."""
        user = User(
            id=uuid4(),
            email=data.email,
            username=data.username,
            full_name=data.full_name,
            hashed_password=_pwd_context.hash(data.password),
            is_active=True,
            is_superuser=False,
            created_at=zoned_utc_now(),
        )
        result = await UserRepository(self._session).create(user)
        return UserDTO.model_validate(result)

    async def update(self, user_id: UUID, data: UserUpdateDTO) -> UserDTO | None:
        """Update a user."""
        repo = UserRepository(self._session)
        user = await repo.find_by_id(user_id)
        if not user:
            return None

        update_data: dict[str, object] = {}
        if data.email is not None:
            update_data["email"] = data.email
        if data.username is not None:
            update_data["username"] = data.username
        if data.full_name is not None:
            update_data["full_name"] = data.full_name
        if data.is_active is not None:
            update_data["is_active"] = data.is_active
        if update_data:
            for key, value in update_data.items():
                setattr(user, key, value)

        result = await repo.update(user)
        return UserDTO.model_validate(result)

    async def delete(self, user_id: UUID) -> bool:
        """Delete a user."""
        repo = UserRepository(self._session)
        user = await repo.find_by_id(user_id)
        if not user:
            return False
        await repo.delete(user.id)
        return True

    async def list_users(self, limit: int = 100, offset: int = 0) -> list[UserDTO]:
        """List users with pagination."""
        results = await UserRepository(self._session).list_all(limit=limit, offset=offset)
        return [UserDTO.model_validate(r) for r in results]

    async def create_user_with_password(self, data: UserCreateWithHashDTO) -> UserDTO:
        """Create a new user with pre-hashed password."""
        user = User(
            id=uuid4(),
            email=data.email,
            hashed_password=data.hashed_password,
            full_name=data.full_name,
            created_at=zoned_utc_now(),
        )
        created = await UserRepository(self._session).create(user)
        return UserDTO.model_validate(created)

    async def update_password(self, user_id: UUID, new_hashed_password: str) -> bool:
        """Update user password."""
        repo = UserRepository(self._session)
        user = await repo.find_by_id(user_id)
        if not user:
            return False
        user.hashed_password = new_hashed_password
        await repo.update(user)
        return True

    async def update_token_version(self, user_id: UUID) -> bool:
        """Increment token version to invalidate old tokens."""
        return await UserRepository(self._session).bump_token_version(user_id)

    async def count_users(self) -> int:
        """Count total users in the system."""
        return await UserRepository(self._session).count_all()

    async def create_admin_user(self, data: UserCreateWithHashDTO) -> UserDTO:
        """Create the first admin user (is_superuser=True)."""
        user = User(
            id=uuid4(),
            email=data.email,
            full_name=data.full_name,
            hashed_password=data.hashed_password,
            is_active=True,
            is_superuser=True,
            created_at=zoned_utc_now(),
        )
        created = await UserRepository(self._session).create(user)
        return UserDTO.model_validate(created)
