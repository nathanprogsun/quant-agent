"""Auth middleware for cookie-based authentication."""

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

if TYPE_CHECKING:
    from app.core.auth.service.auth_service import AuthService


class AuthMiddleware(BaseHTTPMiddleware):
    """Middleware to inject current_user into request state."""

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        # Skip auth for public endpoints
        public_paths = {
            "/api/v1/auth/login",
            "/api/v1/auth/register",
            "/api/v1/auth/csrf",
            "/health",
            "/docs",
            "/openapi.json",
        }

        if request.url.path in public_paths or request.url.path.startswith("/docs"):
            response: Response = await call_next(request)
            return response

        # Get services from app state (set during startup)
        token = request.cookies.get("access_token")
        if token:
            auth_service: AuthService | None = getattr(request.app.state, "auth_service", None)
            if auth_service is None:
                # Skip auth if service not initialized
                return await call_next(request)
            payload = auth_service.decode_token(token)
            if payload:
                user_id = payload.get("sub")
                email = payload.get("email")
                if user_id:
                    request.state.current_user_id = user_id
                    request.state.current_user_email = email

        return await call_next(request)
