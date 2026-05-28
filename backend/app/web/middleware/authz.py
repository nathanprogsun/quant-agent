"""RBAC Authorization middleware and decorators."""

from collections.abc import Callable
from enum import Enum
from functools import wraps
from typing import ParamSpec, TypeVar

from fastapi import Request
from starlette.responses import JSONResponse


class Role(str, Enum):
    """User roles for RBAC."""

    ADMIN = "admin"
    USER = "user"
    GUEST = "guest"


# Resource -> allowed actions mapping
RESOURCE_ACTIONS = {
    "agent": ("read", "write", "delete", "execute"),
    "thread": ("read", "write", "delete"),
    "message": ("read", "write", "delete"),
    "user": ("read", "write", "delete", "manage"),
    "settings": ("read", "write"),
    "billing": ("read", "write"),
}


# Role permissions: role -> set of (resource, actions)
PERMISSIONS: dict[Role, set[tuple[str, ...]]] = {
    Role.ADMIN: {
        ("agent", "read"),
        ("agent", "write"),
        ("agent", "delete"),
        ("agent", "execute"),
        ("thread", "read"),
        ("thread", "write"),
        ("thread", "delete"),
        ("message", "read"),
        ("message", "write"),
        ("message", "delete"),
        ("user", "read"),
        ("user", "write"),
        ("user", "delete"),
        ("user", "manage"),
        ("settings", "read"),
        ("settings", "write"),
        ("billing", "read"),
        ("billing", "write"),
    },
    Role.USER: {
        ("agent", "read"),
        ("agent", "execute"),
        ("thread", "read"),
        ("thread", "write"),
        ("thread", "delete"),
        ("message", "read"),
        ("message", "write"),
        ("message", "delete"),
        ("settings", "read"),
        ("settings", "write"),
    },
    Role.GUEST: {
        ("agent", "read"),
        ("thread", "read"),
        ("message", "read"),
        ("settings", "read"),
    },
}


def get_user_role(request: Request) -> Role:
    """Extract user role from request state.

    Defaults to GUEST if not authenticated or role not set.
    """
    if not hasattr(request.state, "current_user_id"):
        return Role.GUEST

    role_str = getattr(request.state, "current_user_role", None)
    if role_str is None:
        return Role.USER

    try:
        return Role(role_str)
    except ValueError:
        return Role.USER


def has_permission(role: Role, resource: str, action: str, owner_check: bool = False) -> bool:
    """Check if role has permission for resource action.

    Args:
        role: User's role
        resource: Resource name (e.g., 'agent', 'thread')
        action: Action name (e.g., 'read', 'write')
        owner_check: If True, also verify user owns the resource
    """
    if (resource, action) in PERMISSIONS.get(role, set()):
        return True
    return False


P = ParamSpec("P")
T = TypeVar("T")


def require_permission(
    resource: str,
    action: str,
    owner_check: bool = False,
) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """Decorator to require specific permission for an endpoint.

    Args:
        resource: Resource name (e.g., 'agent', 'thread')
        action: Action name (e.g., 'read', 'write')
        owner_check: If True, the decorated endpoint receives `is_owner` kwarg

    Usage:
        @router.post("/agents/{agent_id}")
        @require_permission("agent", "write")
        async def create_agent(request: Request, agent_id: str):
            ...
    """

    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            # Extract request from args/kwargs
            request: Request | None = None
            for arg in args:
                if isinstance(arg, Request):
                    request = arg
                    break
            if request is None:
                request = kwargs.get("request")

            if request is None:
                return JSONResponse(
                    status_code=500,
                    content={"detail": "Request object not found"},
                )

            role = get_user_role(request)

            if not has_permission(role, resource, action, owner_check):
                return JSONResponse(
                    status_code=403,
                    content={
                        "detail": f"Permission denied: {action} on {resource} not allowed for role {role.value}"
                    },
                )

            return await func(*args, **kwargs)

        return wrapper

    return decorator


def require_authenticated() -> Callable[[Callable[P, T]], Callable[P, T]]:
    """Decorator to require authentication.

    Usage:
        @router.get("/profile")
        @require_authenticated()
        async def get_profile(request: Request):
            ...
    """

    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            request: Request | None = None
            for arg in args:
                if isinstance(arg, Request):
                    request = arg
                    break
            if request is None:
                request = kwargs.get("request")

            if request is None:
                return JSONResponse(
                    status_code=500,
                    content={"detail": "Request object not found"},
                )

            if not hasattr(request.state, "current_user_id"):
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Authentication required"},
                )

            return await func(*args, **kwargs)

        return wrapper

    return decorator


def require_role(*roles: Role) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """Decorator to require one of specified roles.

    Usage:
        @router.delete("/users/{user_id}")
        @require_role(Role.ADMIN)
        async def delete_user(request: Request, user_id: str):
            ...
    """

    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            request: Request | None = None
            for arg in args:
                if isinstance(arg, Request):
                    request = arg
                    break
            if request is None:
                request = kwargs.get("request")

            if request is None:
                return JSONResponse(
                    status_code=500,
                    content={"detail": "Request object not found"},
                )

            user_role = get_user_role(request)

            if user_role not in roles:
                return JSONResponse(
                    status_code=403,
                    content={
                        "detail": f"Role required: one of {[r.value for r in roles]}, got {user_role.value}"
                    },
                )

            return await func(*args, **kwargs)

        return wrapper

    return decorator
