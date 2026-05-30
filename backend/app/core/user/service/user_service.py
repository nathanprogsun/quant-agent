"""User service."""

from uuid import UUID, uuid4

from passlib.context import CryptContext

from app.common.exception.exception import ResourceNotFoundError
from app.core.user.types import UserCreateDTO, UserDTO, UserUpdateDTO
from app.db.dao.user_repository import UserRepository
from app.db.dbengine.core import DatabaseEngine
from app.db.models.user import User
from app.util.time import zoned_utc_now

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class UserService:
    """Service for user operations."""

    def __init__(
        self,
        user_repository: UserRepository,
    ):
        self.user_repository = user_repository

    async def get_by_id(self, user_id: UUID) -> UserDTO:
        """Get user by ID."""
        result = await self.user_repository.find_by_primary_key(
            table_model=User,
            id=user_id,
        )
        if not result:
            raise ResourceNotFoundError(f"User with ID {user_id} not found")
        return UserDTO.model_validate(result)

    async def get_by_email(self, email: str) -> UserDTO | None:
        """Get user by email."""
        result = await self.user_repository.find_by_email(email=email)
        return UserDTO.model_validate(result) if result else None

    async def get_user_model_by_id(self, user_id: UUID) -> User | None:
        """Get raw User model by ID (includes hashed_password)."""
        return await self.user_repository.find_by_primary_key(User, id=user_id)

    async def get_user_model_by_email(self, email: str) -> User | None:
        """Get raw User model by email (includes hashed_password)."""
        return await self.user_repository.find_by_email(email=email)

    async def create(self, data: UserCreateDTO) -> UserDTO:
        """Create a new user."""
        # Hash password would be done here in production
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
        result = await self.user_repository.create(user)
        return UserDTO.model_validate(result)

    async def update(self, user_id: UUID, data: UserUpdateDTO) -> UserDTO | None:
        """Update a user."""
        user = await self.user_repository.find_by_primary_key(User, id=user_id)
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
            user = user.model_copy(update=update_data)

        result = await self.user_repository.update(user)
        return UserDTO.model_validate(result)

    async def delete(self, user_id: UUID) -> bool:
        """Delete a user."""
        user = await self.user_repository.find_by_primary_key(User, id=user_id)
        if not user:
            return False
        await self.user_repository.delete(user.id)
        return True

    async def list_users(self, limit: int = 100, offset: int = 0) -> list[UserDTO]:
        """List users with pagination."""
        results: list[User] = await self.user_repository.find_all(
            table_model=User, limit=limit, offset=offset
        )
        return [UserDTO.model_validate(r) for r in results]

    async def create_user_with_password(
        self, email: str, hashed_password: str, full_name: str
    ) -> UserDTO:
        """Create a new user with pre-hashed password."""
        user = User(
            id=uuid4(),
            email=email,
            hashed_password=hashed_password,
            full_name=full_name,
            created_at=zoned_utc_now(),
        )
        created = await self.user_repository.insert(user)
        return UserDTO.model_validate(created)

    async def update_password(self, user_id: UUID, new_hashed_password: str) -> bool:
        """Update user password."""
        user = await self.user_repository.find_by_primary_key(User, id=user_id)
        if not user:
            return False
        user = user.model_copy(update={"hashed_password": new_hashed_password})
        await self.user_repository.update(user)
        return True

    async def update_token_version(self, user_id: UUID) -> bool:
        """Increment token version to invalidate old tokens."""
        user = await self.user_repository.find_by_primary_key(User, id=user_id)
        if not user:
            return False
        user = user.model_copy(update={"token_version": user.token_version + 1})
        await self.user_repository.update(user)
        return True

    async def count_users(self) -> int:
        """Count total users in the system."""
        return await self.user_repository.count_all()

    async def create_admin_user(
        self, email: str, hashed_password: str, full_name: str
    ) -> UserDTO:
        """Create the first admin user (is_superuser=True)."""
        user = User(
            id=uuid4(),
            email=email,
            full_name=full_name,
            hashed_password=hashed_password,
            is_active=True,
            is_superuser=True,
            created_at=zoned_utc_now(),
        )
        created = await self.user_repository.insert(user)
        return UserDTO.model_validate(created)


def get_user_service_by_engine(db_engine: DatabaseEngine) -> UserService:
    """Factory function to create UserService with dependencies."""
    user_repository = UserRepository(engine=db_engine)
    return UserService(user_repository=user_repository)
