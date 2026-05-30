"""Auth middleware for cookie-based authentication."""

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

if TYPE_CHECKING:
    from app.core.auth.service.auth_service import AuthService

# Paths that bypass authentication
PUBLIC_PATHS = frozenset({
    "/api/v1/auth/login",
    "/api/v1/auth/register",
    "/api/v1/auth/initialize",
    "/api/v1/auth/setup-status",
    "/health",
    "/docs",
    "/openapi.json",
})


class AuthMiddleware(BaseHTTPMiddleware):
    """Middleware to inject current_user into request state.

    For non-public paths:
    - Reads access_token cookie
    - Decodes JWT and sets request.state.current_user_id
    - Returns 401 if no valid token present
    """

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        # Skip auth for public endpoints
        if request.url.path in PUBLIC_PATHS or request.url.path.startswith("/docs"):
            return await call_next(request)

        # Get auth service from app context
        app_context = getattr(request.app.state, "app_context", None)
        auth_service: AuthService | None = None
        if app_context:
            lifespan_service = getattr(app_context, "lifespan_service", None)
            if lifespan_service:
                auth_service = getattr(lifespan_service, "auth_service", None)

        if auth_service is None:
            # Service not initialized — let request through (startup race)
            return await call_next(request)

        # Read token from cookie
        token = request.cookies.get("access_token")
        if not token:
            return JSONResponse(
                status_code=401,
                content={"detail": "认证失败或已过期"},
            )

        # Decode and validate
        payload = auth_service.decode_token(token)
        if payload is None:
            return JSONResponse(
                status_code=401,
                content={"detail": "认证失败或已过期"},
            )

        user_id = payload.get("sub")
        if not user_id:
            return JSONResponse(
                status_code=401,
                content={"detail": "认证失败或已过期"},
            )

        # Set user info on request state
        request.state.current_user_id = user_id
        request.state.current_user_email = payload.get("email")
        request.state.token_ver = payload.get("ver", 0)  # Token version for revocation check

        return await call_next(request)
