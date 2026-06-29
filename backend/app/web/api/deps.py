"""Shared API dependencies."""
from typing import Annotated, cast
from uuid import UUID

from fastapi import Depends, Request

from app.common.exception import ResourceNotFoundError, UnauthorizedError
from app.core.auth.service.auth_service import AuthService
from app.core.user.service.user_service import UserService
from app.core.user.types import UserDTO
from app.web.lifespan_service import (
    auth_service_from_request,
    user_service_from_request,
)


def get_current_user_id(request: Request) -> UUID:
    """Get current user UUID from request state set by AuthMiddleware.

    AuthMiddleware already validates the token and sets request.state.current_user_id.
    """
    user_id = getattr(request.state, "current_user_id", None)
    if not user_id:
        raise UnauthorizedError("未认证")
    if isinstance(user_id, str):
        return UUID(user_id)
    return cast(UUID, user_id)


async def get_current_user(
    request: Request,
    user_service: Annotated[UserService, Depends(user_service_from_request)],
    auth_service: AuthService = Depends(auth_service_from_request),
) -> UserDTO:
    """Get the current authenticated user.

    The actual retrieval and version check are delegated to the auth
    service so all auth-related rules live in one place. Missing users
    are surfaced as 401 (not 404) so we don't leak existence state to
    token holders.
    """
    user_id = get_current_user_id(request)
    try:
        user = await user_service.get_by_id(user_id)
    except ResourceNotFoundError as exc:
        # Translate any "not found" into 401 so we don't leak existence
        # state to token holders.
        raise UnauthorizedError("用户不存在") from exc
    token_ver = getattr(request.state, "token_ver", None)
    auth_service.assert_token_version_valid(user, token_ver)
    return user
