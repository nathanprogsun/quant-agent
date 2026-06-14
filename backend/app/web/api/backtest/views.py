"""Backtest API routes."""

from __future__ import annotations

import asyncio
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from app.app_context.app_context import AppContext
from app.core.backtest.errors import BacktestError
from app.core.backtest.registry import BacktestRegistry
from app.core.backtest.service import BacktestService
from app.core.backtest.types import BacktestParams
from app.core.backtest.worker import run_backtest_worker
from app.db.models.user import User
from app.settings import Settings, get_settings
from app.web.api.backtest.schemas import (
    BacktestAbortResponse,
    BacktestMetricsResponse,
    BacktestResultResponse,
    BacktestSubmitRequest,
    BacktestSubmitResponse,
)
from app.web.api.backtest.stream import backtest_sse_consumer, backtest_stream_run_id
from app.web.api.deps import get_current_user

router = APIRouter(prefix="/api/v1/backtest", tags=["backtest"])

_registry = BacktestRegistry()
_worker_tasks: dict[str, asyncio.Task[None]] = {}


def _secret_value(value: object | None) -> str:
    if value is None:
        return ""
    if hasattr(value, "get_secret_value"):
        return str(value.get_secret_value()).strip()
    return str(value).strip()


def get_jqcli_credentials(settings: Settings | None = None) -> tuple[str, str, str] | None:
    """Read jqcli credentials from server env only."""
    cfg = settings or get_settings()
    token = _secret_value(cfg.jqcli_token)
    cookie = _secret_value(cfg.jqcli_cookie)
    if not token and not cookie:
        return None
    return token, cookie, cfg.jqcli_api_base


def get_backtest_service() -> BacktestService:
    """Build BacktestService from server env settings."""
    creds = get_jqcli_credentials()
    if creds is None:
        raise BacktestError(
            message="请先在服务器环境变量中配置 JQCLI_TOKEN 或 JQCLI_COOKIE",
            code="backtest_not_configured",
            status_code=400,
        )
    token, cookie, api_base = creds
    return BacktestService(token=token, cookie=cookie, api_base=api_base)


def _get_app_context(request: Request) -> AppContext:
    app_context = getattr(request.app.state, "app_context", None)
    if app_context is None:
        raise BacktestError(message="服务未就绪", code="service_unavailable", status_code=503)
    return app_context


def _start_backtest_worker(request: Request, backtest_id: str, service: BacktestService) -> None:
    """Spawn background jqcli polling worker for SSE consumers."""
    existing = _worker_tasks.get(backtest_id)
    if existing is not None and not existing.done():
        return

    app_context = _get_app_context(request)
    run_id = backtest_stream_run_id(backtest_id)
    task = asyncio.create_task(
        run_backtest_worker(
            bridge=app_context.stream_bridge,
            service=service,
            backtest_id=backtest_id,
            run_id=run_id,
        ),
        name=f"backtest-{backtest_id}",
    )
    _worker_tasks[backtest_id] = task

    def _cleanup(_task: asyncio.Task[None]) -> None:
        _worker_tasks.pop(backtest_id, None)

    task.add_done_callback(_cleanup)


@router.get("/auth-check")
async def auth_check_get(
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    """Read-only jqcli auth status from server env."""
    creds = get_jqcli_credentials()
    if creds is None:
        return {
            "configured": False,
            "authenticated": False,
            "username": None,
            "message": "未配置 JQCLI_TOKEN 或 JQCLI_COOKIE，请联系管理员",
        }

    service = BacktestService(token=creds[0], cookie=creds[1], api_base=creds[2])
    result = await service.check_auth()
    return {
        "configured": True,
        "authenticated": result.is_authenticated,
        "username": result.username,
        "message": result.message,
    }


@router.post("/auth-check")
async def auth_check_post(
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    """Legacy POST alias for auth-check."""
    return await auth_check_get(current_user)


@router.post("", response_model=BacktestSubmitResponse)
async def submit_backtest(
    body: BacktestSubmitRequest,
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[BacktestService, Depends(get_backtest_service)],
) -> BacktestSubmitResponse:
    """Submit a backtest for execution."""
    thread_key = str(body.thread_id)
    active = _registry.get_active_for_thread(thread_key)
    if active is not None:
        raise BacktestError(
            message="当前会话已有进行中的回测，请等待完成",
            code="backtest_already_running",
            status_code=409,
        )

    params = BacktestParams(
        start_date=body.params.start_date,
        end_date=body.params.end_date,
        initial_capital=body.params.initial_capital,
        frequency=body.params.frequency,
        benchmark=body.params.benchmark,
    )
    backtest_id = await service.submit(
        code=body.code,
        thread_id=body.thread_id,
        version=body.version,
        params=params,
    )
    _registry.register(backtest_id, current_user.id, thread_id=thread_key)
    _start_backtest_worker(request, backtest_id, service)
    return BacktestSubmitResponse(backtest_id=backtest_id)


def _assert_owner(backtest_id: str, user_id: object) -> None:
    """Raise 404 if user does not own the backtest."""
    uid = user_id if isinstance(user_id, UUID) else UUID(str(user_id))
    if not _registry.is_owner(backtest_id, uid):
        raise BacktestError(
            message="回测不存在或无权访问",
            code="backtest_not_found",
            status_code=404,
        )


@router.get("/{backtest_id}", response_model=BacktestResultResponse)
async def get_backtest_result(
    backtest_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[BacktestService, Depends(get_backtest_service)],
) -> BacktestResultResponse:
    """Get backtest result by ID."""
    _assert_owner(backtest_id, current_user.id)
    result = await service.poll(backtest_id)

    metrics_resp = None
    if result.metrics:
        metrics_resp = BacktestMetricsResponse(
            annual_return=result.metrics.annual_return,
            sharpe=result.metrics.sharpe,
            max_drawdown=result.metrics.max_drawdown,
            volatility=result.metrics.volatility,
            win_rate=result.metrics.win_rate,
            raw=result.metrics.raw,
        )

    return BacktestResultResponse(
        backtest_id=result.backtest_id,
        status=result.status.value,
        metrics=metrics_resp,
        error=result.error,
    )


@router.get("/{backtest_id}/stream")
async def stream_backtest(
    backtest_id: str,
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
) -> StreamingResponse:
    """Stream backtest progress events via SSE."""
    _assert_owner(backtest_id, current_user.id)
    app_context = _get_app_context(request)
    run_id = backtest_stream_run_id(backtest_id)
    return StreamingResponse(
        backtest_sse_consumer(app_context.stream_bridge, run_id, request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/{backtest_id}/abort", response_model=BacktestAbortResponse)
async def abort_backtest(
    backtest_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[BacktestService, Depends(get_backtest_service)],
) -> BacktestAbortResponse:
    """Abort a running backtest."""
    _assert_owner(backtest_id, current_user.id)
    success = await service.abort(backtest_id)
    return BacktestAbortResponse(
        success=success,
        message="回测已终止" if success else "回测无法终止",
    )
