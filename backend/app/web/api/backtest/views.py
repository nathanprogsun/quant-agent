"""Backtest API routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.core.backtest.service import BacktestService
from app.core.backtest.types import BacktestParams
from app.core.backtest.errors import BacktestError
from app.web.api.backtest.schemas import (
    BacktestAbortResponse,
    BacktestResultResponse,
    BacktestSubmitRequest,
    BacktestSubmitResponse,
    BacktestMetricsResponse,
)
from app.web.api.deps import get_current_user
from app.db.models.user import User

router = APIRouter(prefix="/api/v1/backtest", tags=["backtest"])


def get_backtest_service(request: Request) -> BacktestService:
    """Get BacktestService from app context."""
    app_context = getattr(request.app.state, "app_context", None)
    settings = getattr(app_context, "settings", None) if app_context else None
    return BacktestService(
        token=getattr(settings, "jqcli_token", "") if settings else "",
        cookie=getattr(settings, "jqcli_cookie", "") if settings else "",
        api_base=getattr(settings, "jqcli_api_base", "https://www.joinquant.com") if settings else "https://www.joinquant.com",
    )


@router.post("", response_model=BacktestSubmitResponse)
async def submit_backtest(
    body: BacktestSubmitRequest,
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
    backtest_id = await service.submit(
        code=body.code,
        thread_id=body.thread_id,
        version=body.version,
        params=params,
    )
    return BacktestSubmitResponse(backtest_id=backtest_id)


@router.get("/{backtest_id}", response_model=BacktestResultResponse)
async def get_backtest_result(
    backtest_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[BacktestService, Depends(get_backtest_service)],
) -> BacktestResultResponse:
    """Get backtest result by ID."""
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


@router.post("/{backtest_id}/abort", response_model=BacktestAbortResponse)
async def abort_backtest(
    backtest_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[BacktestService, Depends(get_backtest_service)],
) -> BacktestAbortResponse:
    """Abort a running backtest."""
    success = await service.abort(backtest_id)
    return BacktestAbortResponse(
        success=success,
        message="回测已终止" if success else "回测无法终止",
    )
