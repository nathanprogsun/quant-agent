"""Backtest API request/response schemas."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


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


class BacktestAuthStatusResponse(BaseModel):
    """Auth-check status combining configured flag with credentials."""

    model_config = ConfigDict(populate_by_name=True)

    is_authenticated: bool = Field(alias="authenticated")
    username: str | None = None
    message: str = ""
    configured: bool = True


class BacktestSimulationResponse(BaseModel):
    """Response for simulation submission."""

    success: bool
    message: str = ""
    simulation_id: str | None = None
    status: str = "submitted"


class BacktestMetricsResponse(BaseModel):
    annual_return: float | None = None
    sharpe: float | None = None
    max_drawdown: float | None = None
    volatility: float | None = None
    win_rate: float | None = None
    total_return: float | None = None
    # Raw upstream payload is opaque — keep it typed-but-flexible.
    raw: dict[str, Any] = Field(default_factory=dict)


class PerformancePointResponse(BaseModel):
    date: str
    strategy: float = 0
    relative: float = 0
    benchmark: float = 0
    position_pct: float | None = None


class TradeRecordResponse(BaseModel):
    symbol: str = ""
    name: str = ""
    side: str = ""
    quantity: float = 0
    price: float = 0


class TradeDayGroupResponse(BaseModel):
    date: str
    trades: list[TradeRecordResponse] = Field(default_factory=list)


class HoldingRecordResponse(BaseModel):
    symbol: str = ""
    name: str = ""
    quantity: float = 0
    avg_cost: float = 0
    close: float = 0
    market_value: float = 0


class HoldingDaySummaryResponse(BaseModel):
    total_assets: float = 0
    cash: float = 0
    total_market_value: float = 0


class HoldingDayGroupResponse(BaseModel):
    date: str
    holdings: list[HoldingRecordResponse] = Field(default_factory=list)
    summary: HoldingDaySummaryResponse = Field(default_factory=HoldingDaySummaryResponse)


class BacktestResultResponse(BaseModel):
    backtest_id: str
    status: str
    metrics: BacktestMetricsResponse | None = None
    performance: list[PerformancePointResponse] = Field(default_factory=list)
    trades: list[TradeDayGroupResponse] = Field(default_factory=list)
    holdings: list[HoldingDayGroupResponse] = Field(default_factory=list)
    error: str | None = None


class BacktestAbortResponse(BaseModel):
    success: bool
    message: str = ""


class BacktestThreadCancelResponse(BaseModel):
    """Response for canceling the active backtest lock on a thread."""

    cancelled: bool
    backtest_id: str | None = None
    message: str = ""
