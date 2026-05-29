"""Backtest data types."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class BacktestStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class BacktestParams:
    """Backtest configuration parameters."""
    start_date: str = "2020-01-01"
    end_date: str = "2024-12-31"
    initial_capital: float = 100000.0
    frequency: str = "day"  # day, minute
    benchmark: str = "000300.XSHG"


@dataclass(frozen=True)
class BacktestMetrics:
    """Backtest result metrics."""
    annual_return: float | None = None
    sharpe: float | None = None
    max_drawdown: float | None = None
    volatility: float | None = None
    win_rate: float | None = None
    profit_loss_ratio: float | None = None
    turnover: float | None = None
    alpha: float | None = None
    beta: float | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BacktestResult:
    """Complete backtest result."""
    backtest_id: str
    status: BacktestStatus
    metrics: BacktestMetrics | None = None
    error: str | None = None


@dataclass(frozen=True)
class AuthResult:
    """jqcli authentication check result."""
    is_authenticated: bool
    username: str | None = None
    message: str = ""
