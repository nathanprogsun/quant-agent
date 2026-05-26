import contextlib
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.user.service.user_service import UserService, get_user_service_by_engine
from app.core.user.types import UserDTO
from app.db.dbengine.core import DatabaseEngine
from app.settings import get_settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _convert_to_json_serializable(data: dict[str, Any]) -> dict[str, Any]:
    """Convert UUID and other non-JSON-serializable objects to strings."""
    result: dict[str, Any] = {}
    for key, value in data.items():
        if isinstance(value, UUID):
            result[key] = str(value)
        elif isinstance(value, datetime):
            result[key] = value.isoformat()
        else:
            result[key] = value
    return result


class AuthService:
    def __init__(self, user_service: UserService) -> None:
        self.user_service = user_service

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        return pwd_context.verify(plain_password, hashed_password)

    def get_password_hash(self, password: str) -> str:
        return pwd_context.hash(password)

    def create_access_token(self, data: dict[str, Any], expires_delta: timedelta | None = None) -> str:
        settings = get_settings()
        to_encode = _convert_to_json_serializable(data)
        expire = datetime.now(UTC) + (
            expires_delta or timedelta(minutes=settings.jwt_expire_minutes)
        )
        to_encode.update({"exp": expire})
        return jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)

    def create_csrf_token(self) -> str:
        """Generate a CSRF token using UUID4."""
        return str(uuid4())

    async def authenticate_user(self, email: str, password: str) -> UserDTO | None:
        user = await self.user_service.get_user_model_by_email(email)
        if not user:
            return None
        if not self.verify_password(password, user.hashed_password):
            return None
        return UserDTO.model_validate(user)

    async def register_user(self, email: str, password: str, full_name: str) -> UserDTO:
        hashed_password = self.get_password_hash(password)
        return await self.user_service.create_user_with_password(email, hashed_password, full_name)

    def decode_token(self, token: str) -> dict[str, Any] | None:
        settings = get_settings()
        try:
            payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
            # Convert sub back to UUID if it's a valid UUID string
            if "sub" in payload:
                with contextlib.suppress(ValueError, TypeError):
                    payload["sub"] = UUID(payload["sub"])
            return payload
        except JWTError:
            return None

    async def change_password(self, user_id: UUID, old_password: str, new_password: str) -> bool:
        """Change user password. Returns True if successful."""
        user = await self.user_service.get_user_model_by_id(user_id)
        if not user:
            return False
        if not self.verify_password(old_password, user.hashed_password):
            return False
        new_hash = self.get_password_hash(new_password)
        await self.user_service.update_password(user_id, new_hash)
        return True


def get_auth_service_by_engine(db_engine: DatabaseEngine) -> AuthService:
    """Factory function to create AuthService with dependencies."""
    return AuthService(user_service=get_user_service_by_engine(db_engine))
