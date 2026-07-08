"""Backtest API routes."""

from __future__ import annotations

import asyncio
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from app.app_context.app_context import AppContext
from app.core.backtest.jqcli_auth import JqcliNotConfiguredError, resolve_jqcli_credentials_tuple
from app.core.backtest.service import BacktestService
from app.core.backtest.types import BacktestParams
from app.core.backtest.worker import run_backtest_worker
from app.db.models.user import User
from app.settings import get_settings
from app.web.api.backtest.schemas import (
    BacktestAbortResponse,
    BacktestAuthStatusResponse,
    BacktestMetricsResponse,
    BacktestResultResponse,
    BacktestSimulationResponse,
    BacktestSubmitRequest,
    BacktestSubmitResponse,
    BacktestThreadCancelResponse,
    HoldingDayGroupResponse,
    HoldingDaySummaryResponse,
    HoldingRecordResponse,
    PerformancePointResponse,
    TradeDayGroupResponse,
    TradeRecordResponse,
)
from app.web.api.backtest.stream import backtest_sse_consumer, backtest_stream_run_id
from app.web.api.deps import get_current_user
from app.web.lifespan_service import backtest_service_from_request
from app.web.lifespan_service import get_app_context as _get_app_context

router = APIRouter(prefix="/api/v1/backtest", tags=["backtest"])

_worker_tasks: dict[str, asyncio.Task[None]] = {}


def _reap_stale_thread_lock(service: BacktestService, thread_id: UUID) -> None:
    """If a thread is marked active but its worker task is gone, clear the lock.

    Prevents a permanently stuck "already running" state when a worker task
    died (crashed/cancelled) without the registry being cleaned up.
    """
    active_id = service.get_active_for_thread(thread_id)
    if active_id is None:
        return
    task = _worker_tasks.get(active_id)
    if task is None or task.done():
        service.cancel_for_thread(thread_id)


def _start_backtest_worker(
    app_context: AppContext,
    backtest_id: str,
    service: BacktestService,
) -> None:
    """Spawn background jqcli polling worker for SSE consumers."""
    existing = _worker_tasks.get(backtest_id)
    if existing is not None and not existing.done():
        return

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
    cfg = get_settings()
    try:
        creds = resolve_jqcli_credentials_tuple(cfg)
    except JqcliNotConfiguredError:
        return BacktestAuthStatusResponse(
            authenticated=False,
            username=None,
            message="未配置 JQCLI_USERNAME/JQCLI_PASSWORD，请联系管理员",
            configured=False,
        )
    except RuntimeError as exc:
        return BacktestAuthStatusResponse(
            authenticated=False,
            username=None,
            message=str(exc),
            configured=True,
        )
    if creds is None:
        return BacktestAuthStatusResponse(
            authenticated=False,
            username=None,
            message="聚宽登录失败，请检查 JQCLI_USERNAME/JQCLI_PASSWORD",
            configured=True,
        )
    token, cookie, api_base = creds
    service = BacktestService(token=token, cookie=cookie, api_base=api_base)
    status = await service.check_auth_status()
    return BacktestAuthStatusResponse(
        authenticated=status.authenticated,
        username=status.username,
        message=status.message,
        configured=True,
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
    service: Annotated[BacktestService, Depends(backtest_service_from_request)],
) -> BacktestSubmitResponse:
    """Submit a backtest for execution."""
    _reap_stale_thread_lock(service, body.thread_id)
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
    app_context = _get_app_context(request)
    _start_backtest_worker(app_context, backtest_id, service)
    return BacktestSubmitResponse(backtest_id=backtest_id)


@router.get("/{backtest_id}", response_model=BacktestResultResponse)
async def get_backtest_result(
    backtest_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[BacktestService, Depends(backtest_service_from_request)],
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
    service: Annotated[BacktestService, Depends(backtest_service_from_request)],
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


@router.post(
    "/{backtest_id}/simulation",
    response_model=BacktestSimulationResponse,
    deprecated=True,
)
async def submit_simulation(
    backtest_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[BacktestService, Depends(backtest_service_from_request)],
) -> BacktestSimulationResponse:
    """Deprecated: simulation submit is not supported in the current product scope."""
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
    service: Annotated[BacktestService, Depends(backtest_service_from_request)],
) -> BacktestAbortResponse:
    """Abort a running backtest."""
    result = await service.abort_for_user(backtest_id, current_user.id)
    return BacktestAbortResponse(success=result.success, message=result.message)


@router.post("/threads/{thread_id}/cancel", response_model=BacktestThreadCancelResponse)
async def cancel_thread_backtest(
    thread_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[BacktestService, Depends(backtest_service_from_request)],
) -> BacktestThreadCancelResponse:
    """Cancel the active backtest lock for a thread.

    jqcli does not support aborting the remote backtest, but this releases the
    local "already running" lock so the user can submit a new one. If a worker
    task is still polling, it is cancelled locally (the remote backtest will
    finish on its own; we simply stop watching it).
    """
    backtest_id = service.cancel_for_thread(thread_id)
    if backtest_id is None:
        return BacktestThreadCancelResponse(
            cancelled=False,
            message="该会话没有进行中的回测",
        )
    task = _worker_tasks.pop(backtest_id, None)
    if task is not None and not task.done():
        task.cancel()
    return BacktestThreadCancelResponse(
        cancelled=True,
        backtest_id=backtest_id,
        message="已取消该会话的回测占用，可重新提交",
    )
