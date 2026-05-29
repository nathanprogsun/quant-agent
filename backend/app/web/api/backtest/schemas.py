"""Backtest API request/response schemas."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class BacktestParamsInput(BaseModel):
    start_date: str = "2020-01-01"
    end_date: str = "2024-12-31"
    initial_capital: float = 100000.0
    frequency: str = "day"
    benchmark: str = "000300.XSHG"


MAX_CODE_LENGTH = 65536  # 64KB


class BacktestSubmitRequest(BaseModel):
    code: str = Field(..., max_length=MAX_CODE_LENGTH)
    thread_id: UUID
    version: int = 1
    params: BacktestParamsInput = Field(default_factory=BacktestParamsInput)


class BacktestSubmitResponse(BaseModel):
    backtest_id: str


class BacktestMetricsResponse(BaseModel):
    annual_return: float | None = None
    sharpe: float | None = None
    max_drawdown: float | None = None
    volatility: float | None = None
    win_rate: float | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class BacktestResultResponse(BaseModel):
    backtest_id: str
    status: str
    metrics: BacktestMetricsResponse | None = None
    error: str | None = None


class BacktestAbortResponse(BaseModel):
    success: bool
    message: str = ""
