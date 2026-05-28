"""Shared API dependencies."""

from fastapi import Depends, HTTPException, Request, status

from app.core.user.service.user_service import UserService
from app.core.user.types import UserDTO
from app.web.lifespan_service import user_service_from_lifespan


def get_current_user_id(request: Request) -> str:
    """Get current user ID from request state set by AuthMiddleware.

    AuthMiddleware already validates the token and sets request.state.current_user_id.
    """
    user_id = getattr(request.state, "current_user_id", None)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未认证",
        )
    return user_id


async def get_current_user(
    request: Request,
    user_service: UserService = Depends(user_service_from_lifespan),
) -> UserDTO:
    """Get the current authenticated user."""
    user_id = get_current_user_id(request)
    user = await user_service.get_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在",
        )
    return user