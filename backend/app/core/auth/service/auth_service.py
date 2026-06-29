from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.common.exception.exception import (
    ResourceNotFoundError,
    UnauthorizedError,
)
from app.core.auth.types import TokenClaims
from app.core.user.service.user_service import UserService
from app.core.user.types import UserCreateWithHashDTO, UserDTO
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
    """Auth service — wraps UserService for auth-specific operations.

    Receives a UserService (which shares the per-request session).
    """

    def __init__(self, user_service: UserService) -> None:
        self.user_service = user_service

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        return pwd_context.verify(plain_password, hashed_password)

    def get_password_hash(self, password: str) -> str:
        return pwd_context.hash(password)

    def create_access_token(
        self,
        data: TokenClaims,
        expires_delta: timedelta | None = None,
        token_version: int = 0,
    ) -> str:
        settings = get_settings()
        to_encode = _convert_to_json_serializable(data.model_dump(mode="python"))
        expire = datetime.now(UTC) + (
            expires_delta or timedelta(minutes=settings.jwt_expire_minutes)
        )
        to_encode.update(
            {
                "exp": expire,
                "ver": token_version,
                "iss": settings.jwt_issuer,
                "aud": settings.jwt_audience,
            }
        )
        return jwt.encode(
            to_encode, settings.jwt_secret_key.get_secret_value(), algorithm=settings.jwt_algorithm
        )

    async def authenticate_user(self, email: str, password: str) -> UserDTO:
        """Authenticate user; raise UnauthorizedError on bad credentials."""
        user = await self.user_service.get_user_model_by_email(email)
        if not user or not self.verify_password(password, user.hashed_password):
            raise UnauthorizedError("Incorrect email or password")
        return UserDTO.model_validate(user)

    async def register_user(self, email: str, password: str, full_name: str) -> UserDTO:
        hashed_password = self.get_password_hash(password)
        return await self.user_service.create_user_with_password(
            UserCreateWithHashDTO(
                email=email,
                hashed_password=hashed_password,
                full_name=full_name,
            )
        )

    def decode_token(self, token: str) -> TokenClaims | None:
        settings = get_settings()
        try:
            payload = jwt.decode(
                token,
                settings.jwt_secret_key.get_secret_value(),
                algorithms=[settings.jwt_algorithm],
                audience=settings.jwt_audience,
                issuer=settings.jwt_issuer,
            )
            return TokenClaims.model_validate(payload)
        except (JWTError, ValueError, TypeError):
            return None

    async def change_password(self, user_id: UUID, old_password: str, new_password: str) -> None:
        """Change password; raise UnauthorizedError on bad old password."""
        user = await self.user_service.get_user_model_by_id(user_id)
        if not user:
            raise ResourceNotFoundError(f"User {user_id} not found")
        if not self.verify_password(old_password, user.hashed_password):
            raise UnauthorizedError("Invalid old password")
        new_hash = self.get_password_hash(new_password)
        await self.user_service.update_password(user_id, new_hash)

    async def change_password_and_emit_claims(
        self, user_id: UUID, old_password: str, new_password: str
    ) -> tuple[TokenClaims, int]:
        """Change password + bump token_version + return (claims, new_ver).

        Returns the freshly-bumped token_version alongside the user
        claims so the caller can mint a new access token without an
        extra DB round-trip.
        """
        await self.change_password(user_id, old_password, new_password)
        await self.user_service.update_token_version(user_id)
        user = await self.user_service.get_user_model_by_id(user_id)
        assert user is not None  # we just changed its password
        return TokenClaims(sub=user.id, email=user.email), user.token_version

    def assert_token_version_valid(
        self, user: UserDTO, token_ver: int | None
    ) -> None:
        """Verify token's ver matches user's current token_version."""
        if token_ver is not None and user.token_version != token_ver:
            raise UnauthorizedError("Token已失效，请重新登录")
