"""Analyze API request/response schemas."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class AnalyzeMetricsInput(BaseModel):
    annual_return: float | None = None
    sharpe: float | None = None
    max_drawdown: float | None = None
    volatility: float | None = None
    win_rate: float | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class AnalyzeStreamRequest(BaseModel):
    thread_id: UUID
    backtest_id: str = ""
    code: str = Field(default="", max_length=65536)
    metrics: AnalyzeMetricsInput
