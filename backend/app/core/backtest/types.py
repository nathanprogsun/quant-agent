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
    total_return: float | None = None
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


@dataclass(frozen=True)
class PerformancePoint:
    """A single point on the performance series."""

    date: str
    strategy: float = 0.0
    relative: float = 0.0
    benchmark: float = 0.0
    position_pct: float | None = None


@dataclass(frozen=True)
class TradeRecord:
    """A single trade record."""

    symbol: str = ""
    name: str = ""
    side: str = ""
    quantity: float = 0.0
    price: float = 0.0


@dataclass(frozen=True)
class TradeDayGroup:
    """Trades grouped by date."""

    date: str
    trades: list[TradeRecord] = field(default_factory=list)


@dataclass(frozen=True)
class HoldingRecord:
    """A single holding record."""

    symbol: str = ""
    name: str = ""
    quantity: float = 0.0
    avg_cost: float = 0.0
    close: float = 0.0
    market_value: float = 0.0


@dataclass(frozen=True)
class HoldingDaySummary:
    """Per-day holding summary."""

    total_assets: float = 0.0
    cash: float = 0.0
    total_market_value: float = 0.0


@dataclass(frozen=True)
class HoldingDayGroup:
    """Holdings grouped by date."""

    date: str
    holdings: list[HoldingRecord] = field(default_factory=list)
    summary: HoldingDaySummary = field(default_factory=HoldingDaySummary)


@dataclass(frozen=True)
class BacktestResultDetail:
    """Full backtest detail ready for API response."""

    backtest_id: str
    status: BacktestStatus
    metrics: BacktestMetrics | None = None
    performance: list[PerformancePoint] = field(default_factory=list)
    trades: list[TradeDayGroup] = field(default_factory=list)
    holdings: list[HoldingDayGroup] = field(default_factory=list)
    error: str | None = None


@dataclass(frozen=True)
class BacktestAbortResult:
    """Outcome of an abort request."""

    success: bool
    message: str = ""


@dataclass(frozen=True)
class BacktestSimulationResult:
    """Outcome of a simulation submission."""

    success: bool
    task_id: str
    status: str = "submitted"
    message: str = ""


@dataclass(frozen=True)
class BacktestLogResult:
    """Incremental log fetch result."""

    logs: list[str] = field(default_factory=list)
    next_offset: int = 0


@dataclass(frozen=True)
class BacktestAuthStatus:
    """Auth check status combining configured flag with credentials."""

    configured: bool
    authenticated: bool
    username: str | None
    message: str = ""
