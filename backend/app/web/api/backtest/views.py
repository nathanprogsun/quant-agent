"""Backtest API routes."""

from __future__ import annotations

import asyncio
from typing import Annotated, cast

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from app.app_context.app_context import AppContext
from app.core.backtest.errors import BacktestError
from app.core.backtest.service import BacktestService
from app.core.backtest.types import BacktestParams
from app.core.backtest.worker import run_backtest_worker
from app.db.models.user import User
from app.settings import Settings, get_settings
from app.web.api.backtest.schemas import (
    BacktestAbortResponse,
    BacktestAuthStatusResponse,
    BacktestMetricsResponse,
    BacktestResultResponse,
    BacktestSimulationResponse,
    BacktestSubmitRequest,
    BacktestSubmitResponse,
    HoldingDayGroupResponse,
    HoldingDaySummaryResponse,
    HoldingRecordResponse,
    PerformancePointResponse,
    TradeDayGroupResponse,
    TradeRecordResponse,
)
from app.web.api.backtest.stream import backtest_sse_consumer, backtest_stream_run_id
from app.web.api.deps import get_current_user

router = APIRouter(prefix="/api/v1/backtest", tags=["backtest"])

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
    return cast(AppContext, app_context)


def _start_backtest_worker(request: Request, backtest_id: str, service: BacktestService) -> None:
    """Spawn background jqcli polling worker for SSE consumers."""
    existing = _worker_tasks.get(backtest_id)
    if existing is not None and not existing.done():
        return

    app_context = _get_app_context(request)
    run_id = backtest_stream_run_id(backtest_id)
    assert app_context.stream_bridge is not None  # always set at startup
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


@router.get("/auth-check", response_model=BacktestAuthStatusResponse)
async def auth_check_get(
    current_user: Annotated[User, Depends(get_current_user)],
) -> BacktestAuthStatusResponse:
    """Read-only jqcli auth status from server env.

    Returns `configured=False` when no credentials are configured rather
    than 400 — clients (the setup wizard) need to distinguish the two.
    """
    creds = get_jqcli_credentials()
    if creds is None:
        return BacktestAuthStatusResponse(
            authenticated=False,
            username=None,
            message="未配置 JQCLI_TOKEN 或 JQCLI_COOKIE，请联系管理员",
            configured=False,
        )
    token, cookie, api_base = creds
    service = BacktestService(token=token, cookie=cookie, api_base=api_base)
    status = await service.check_auth_status()
    return BacktestAuthStatusResponse(
        authenticated=status.authenticated,
        username=status.username,
        message=status.message,
        configured=status.configured,
    )


@router.post("/auth-check", response_model=BacktestAuthStatusResponse)
async def auth_check_post(
    current_user: Annotated[User, Depends(get_current_user)],
) -> BacktestAuthStatusResponse:
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
    params = BacktestParams(
        start_date=body.params.start_date,
        end_date=body.params.end_date,
        initial_capital=body.params.initial_capital,
        frequency=body.params.frequency,
        benchmark=body.params.benchmark,
    )
    backtest_id = await service.submit_for_user(
        user_id=current_user.id,
        thread_id=body.thread_id,
        code=body.code,
        version=body.version,
        params=params,
    )
    _start_backtest_worker(request, backtest_id, service)
    return BacktestSubmitResponse(backtest_id=backtest_id)


@router.get("/{backtest_id}", response_model=BacktestResultResponse)
async def get_backtest_result(
    backtest_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[BacktestService, Depends(get_backtest_service)],
) -> BacktestResultResponse:
    """Get backtest result by ID."""
    detail = await service.get_result_detail_for_user(backtest_id, current_user.id)

    metrics_resp = None
    if detail.metrics:
        metrics_resp = BacktestMetricsResponse(
            annual_return=detail.metrics.annual_return,
            sharpe=detail.metrics.sharpe,
            max_drawdown=detail.metrics.max_drawdown,
            volatility=detail.metrics.volatility,
            win_rate=detail.metrics.win_rate,
            total_return=detail.metrics.total_return,
            raw=detail.metrics.raw,
        )

    return BacktestResultResponse(
        backtest_id=detail.backtest_id,
        status=detail.status.value,
        metrics=metrics_resp,
        performance=[PerformancePointResponse(**p.__dict__) for p in detail.performance],
        trades=[
            TradeDayGroupResponse(
                date=g.date,
                trades=[TradeRecordResponse(**t.__dict__) for t in g.trades],
            )
            for g in detail.trades
        ],
        holdings=[
            HoldingDayGroupResponse(
                date=g.date,
                holdings=[HoldingRecordResponse(**h.__dict__) for h in g.holdings],
                summary=HoldingDaySummaryResponse(**g.summary.__dict__),
            )
            for g in detail.holdings
        ],
        error=detail.error,
    )


@router.get("/{backtest_id}/stream")
async def stream_backtest(
    backtest_id: str,
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[BacktestService, Depends(get_backtest_service)],
) -> StreamingResponse:
    """Stream backtest progress events via SSE."""
    service.assert_owner(backtest_id, current_user.id)
    app_context = _get_app_context(request)
    run_id = backtest_stream_run_id(backtest_id)
    assert app_context.stream_bridge is not None  # always set at startup
    return StreamingResponse(
        backtest_sse_consumer(app_context.stream_bridge, run_id, request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/{backtest_id}/simulation", response_model=BacktestSimulationResponse)
async def submit_simulation(
    backtest_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[BacktestService, Depends(get_backtest_service)],
) -> BacktestSimulationResponse:
    """Submit simulation stub — jqcli simulation wiring deferred."""
    result = await service.submit_simulation_for_user(backtest_id, current_user.id)
    return BacktestSimulationResponse(
        success=result.success,
        message=result.message,
        simulation_id=result.task_id,
        status=result.status,
    )


@router.post("/{backtest_id}/abort", response_model=BacktestAbortResponse)
async def abort_backtest(
    backtest_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[BacktestService, Depends(get_backtest_service)],
) -> BacktestAbortResponse:
    """Abort a running backtest."""
    result = await service.abort_for_user(backtest_id, current_user.id)
    return BacktestAbortResponse(success=result.success, message=result.message)
