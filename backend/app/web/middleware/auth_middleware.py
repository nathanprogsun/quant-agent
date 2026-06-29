"""Auth middleware for cookie-based authentication.

Decodes the JWT access_token cookie and sets request.state.current_user_id
for downstream dependencies (see app.web.api.deps.get_current_user_id).
Uses the stateless decode_access_token — no AuthService instance required,
since AuthService is constructed per-request and would create a circular
dependency on session_factory setup.
"""

from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.core.auth.service.auth_service import decode_access_token

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

        # Read token from cookie
        token = request.cookies.get("access_token")
        if not token:
            return JSONResponse(
                status_code=401,
                content={"detail": "认证失败或已过期"},
            )

        # Decode and validate
        payload = decode_access_token(token)
        if payload is None:
            return JSONResponse(
                status_code=401,
                content={"detail": "认证失败或已过期"},
            )

        # Set user info on request state
        request.state.current_user_id = payload.sub
        request.state.current_user_email = payload.email
        # `ver` is an optional claim minted alongside exp/iss/aud
        request.state.token_ver = getattr(payload, "ver", 0)

        return await call_next(request)
