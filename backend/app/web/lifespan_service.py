"""Per-request service dependency injection helpers.

Standard FastAPI + SQLAlchemy 2.0 pattern: one AsyncSession per request,
services share that session, FastAPI commits at request end.
"""

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from app.app_context.app_context import AppContext
from app.common.exception import IllegalStateError, ServiceError
from app.core.auth.service.auth_service import AuthService
from app.core.backtest.errors import BacktestError
from app.core.backtest.jqcli_auth import JqcliNotConfiguredError, resolve_jqcli_credentials_tuple
from app.core.backtest.registry import BacktestRegistry
from app.core.backtest.service import BacktestService
from app.core.chat.memory.service import MemoryService
from app.core.chat.service.thread_service import RunService, ThreadService
from app.core.user.service.user_service import UserService
from app.settings import get_settings

# ── App-level accessors ──────────────────────────────────────────


def get_app_context(request: Request) -> AppContext:
    """Retrieve the AppContext from app state."""
    app_context = getattr(request.app.state, "app_context", None)
    if not isinstance(app_context, AppContext):
        raise IllegalStateError(
            f"expected app_context to be of type {AppContext}, but got {type(app_context)}"
        )
    return app_context


# ── Session-per-request (with commit/rollback boundary) ──────────


async def session_from_app_context(
    app_context: Annotated[AppContext, Depends(get_app_context)],
) -> AsyncIterator[AsyncSession]:
    """Yield a per-request AsyncSession. Commits on success, rolls back on exception.

    This is the single boundary where transactions are committed. All
    services and repositories receiving this session share one transaction
    for the duration of the request, so multi-step operations are atomic.
    """
    async with app_context.session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# ── Per-request service factories ────────────────────────────────


def user_service_from_request(
    session: Annotated[AsyncSession, Depends(session_from_app_context)],
) -> UserService:
    """Build a UserService bound to the request's session."""
    return UserService(session=session)


def thread_service_from_request(
    session: Annotated[AsyncSession, Depends(session_from_app_context)],
) -> ThreadService:
    """Build a ThreadService bound to the request's session."""
    return ThreadService(session=session)


def run_service_from_request(
    app_context: Annotated[AppContext, Depends(get_app_context)],
) -> RunService:
    """Build a RunService bound to the app's RunManager.

    Raises:
        ServiceError: if the RunManager is not configured on the AppContext.
    """
    if app_context.run_manager is None:
        raise ServiceError("RunManager not available")
    return RunService(run_manager=app_context.run_manager)


def auth_service_from_request(
    user_service: Annotated[UserService, Depends(user_service_from_request)],
) -> AuthService:
    """Build an AuthService that shares the request's session via UserService."""
    return AuthService(user_service=user_service)


def memory_service_from_request(
    session: Annotated[AsyncSession, Depends(session_from_app_context)],
) -> MemoryService:
    """Build a MemoryService bound to the request's session."""
    return MemoryService(session=session)


def backtest_service_from_request(
    app_context: Annotated[AppContext, Depends(get_app_context)],
) -> BacktestService:
    """Build BacktestService with credentials from env and shared registry.

    The ownership registry is read from the shared ``AppContext`` so that the
    submit endpoint and the SSE stream endpoint — which are independent
    requests — agree on which user owns which backtest.
    """
    cfg = get_settings()
    try:
        creds = resolve_jqcli_credentials_tuple(cfg)
    except JqcliNotConfiguredError:
        raise BacktestError(
            message="请先在服务器环境变量中配置 JQCLI_USERNAME 和 JQCLI_PASSWORD",
            code="backtest_not_configured",
            status_code=400,
        )
    if creds is None:
        raise BacktestError(
            message="聚宽登录失败，请检查 JQCLI_USERNAME/JQCLI_PASSWORD 是否正确",
            code="backtest_auth_failed",
            status_code=400,
        )
    token, cookie, api_base = creds
    registry = app_context.backtest_registry or BacktestRegistry()
    return BacktestService(
        token=token,
        cookie=cookie,
        api_base=api_base,
        registry=registry,
    )
