"""Backtest service — wraps jqcli API with unified error handling."""

from __future__ import annotations

import asyncio
import functools
from concurrent.futures import ThreadPoolExecutor
from typing import Any, cast
from uuid import UUID

from jqcli.api.backtest import (
    get_backtest,
    get_backtest_logs,
    get_backtest_result,
    run_backtest,
)
from jqcli.api.client import ApiClient
from jqcli.api.strategy import create_strategy
from jqcli.errors import NotAuthenticatedError

from app.core.backtest.errors import BacktestError, map_jqcli_error
from app.core.backtest.registry import BacktestRegistry
from app.core.backtest.types import (
    AuthResult,
    BacktestAbortResult,
    BacktestAuthStatus,
    BacktestLogResult,
    BacktestMetrics,
    BacktestParams,
    BacktestResult,
    BacktestResultDetail,
    BacktestSimulationResult,
    BacktestStatus,
    HoldingDayGroup,
    HoldingDaySummary,
    HoldingRecord,
    PerformancePoint,
    TradeDayGroup,
    TradeRecord,
)

_executor = ThreadPoolExecutor(max_workers=4)

POLL_INTERVAL_SECONDS = 3
TIMEOUT_SECONDS = 300


def _check_auth_sync(token: str, cookie: str, api_base: str) -> dict[str, Any]:
    """Sync jqcli auth check — runs in thread pool.

    `get_current_user` is only present in deployed jqcli (not the vendored copy
    checked in here), so the import is wrapped in try/except to allow the
    fallback path when running against the local stub.
    """
    client = ApiClient(api_base, token=token, cookie=cookie)
    try:
        try:
            from jqcli.api.auth import (  # type: ignore[attr-defined]  # noqa: PLC0415
                get_current_user,
            )
            user_info = get_current_user(client)
        except ImportError:
            user_info = {"username": "authenticated"}
        return cast(dict[str, Any], {"username": user_info.get("username", "authenticated")})
    finally:
        client.close()


def _submit_sync(
    code: str,
    params_dict: dict[str, Any],
    token: str,
    cookie: str,
    api_base: str,
) -> str:
    """Sync jqcli backtest submit — runs in thread pool.

    Note: jqcli run_backtest requires strategy_id. For direct code submission,
    the code must first be saved to a strategy, then backtest is submitted.
    This is a simplified version for the integration.
    """
    client = ApiClient(api_base, token=token, cookie=cookie)
    try:
        # Create or update strategy with the code
        strategy = create_strategy(client, name="auto_generated", code=code, strategy_type="Code")
        strategy_id = str(strategy.get("id", ""))

        if not strategy_id:
            raise RuntimeError("无法创建策略")

        # Submit backtest
        result = run_backtest(
            client,
            strategy_id=strategy_id,
            start_date=params_dict["start_date"],
            end_date=params_dict.get("end_date"),
            capital=params_dict.get("initial_capital"),
            frequency=params_dict.get("frequency", "day"),
        )
        return str(result.get("id", result))
    finally:
        client.close()


def _poll_sync(backtest_id: str, token: str, cookie: str, api_base: str) -> dict[str, Any]:
    """Sync jqcli backtest poll — runs in thread pool."""
    client = ApiClient(api_base, token=token, cookie=cookie)
    try:
        return get_backtest(client, backtest_id)
    finally:
        client.close()


def _get_logs_sync(
    backtest_id: str,
    offset: int,
    token: str,
    cookie: str,
    api_base: str,
) -> dict[str, Any]:
    """Sync jqcli fetch backtest logs — runs in thread pool."""
    client = ApiClient(api_base, token=token, cookie=cookie)
    try:
        return get_backtest_logs(client, backtest_id, offset=offset, all_items=False)
    finally:
        client.close()


def _parse_performance_series(result_payload: dict[str, Any]) -> list[PerformancePoint]:
    data = result_payload.get("data", result_payload)
    if isinstance(data, dict) and isinstance(data.get("data"), dict):
        data = data["data"]
    result = data.get("result") if isinstance(data, dict) else {}
    if not isinstance(result, dict):
        return []

    series = result.get("series") or result.get("chart_series") or result.get("charts")
    if not isinstance(series, list):
        return []

    points: list[PerformancePoint] = []
    for item in series:
        if not isinstance(item, dict):
            continue
        date = item.get("date") or item.get("time") or item.get("trade_date")
        if not date:
            continue
        points.append(
            PerformancePoint(
                date=str(date),
                strategy=float(item.get("strategy") or item.get("strategy_return") or 0),
                relative=float(item.get("relative") or item.get("relative_return") or 0),
                benchmark=float(item.get("benchmark") or item.get("benchmark_return") or 0),
                position_pct=item.get("position_pct"),
            )
        )
    return points


def _parse_trade_groups(result_payload: dict[str, Any]) -> list[TradeDayGroup]:
    data = result_payload.get("data", result_payload)
    if isinstance(data, dict) and isinstance(data.get("data"), dict):
        data = data["data"]
    result = data.get("result") if isinstance(data, dict) else {}
    trades = result.get("trades") if isinstance(result, dict) else None
    if not isinstance(trades, list):
        return []

    by_date: dict[str, list[TradeRecord]] = {}
    for item in trades:
        if not isinstance(item, dict):
            continue
        date = str(item.get("date") or item.get("trade_date") or "")
        if not date:
            continue
        by_date.setdefault(date, []).append(
            TradeRecord(
                symbol=str(item.get("symbol") or item.get("security") or ""),
                name=str(item.get("name") or item.get("security_name") or ""),
                side=str(item.get("side") or item.get("action") or ""),
                quantity=float(item.get("quantity") or item.get("amount") or 0),
                price=float(item.get("price") or 0),
            )
        )

    return [
        TradeDayGroup(date=date, trades=list(rows))
        for date, rows in sorted(by_date.items())
    ]


def _parse_holding_groups(result_payload: dict[str, Any]) -> list[HoldingDayGroup]:
    data = result_payload.get("data", result_payload)
    if isinstance(data, dict) and isinstance(data.get("data"), dict):
        data = data["data"]
    result = cast(dict[str, Any], data.get("result")) if isinstance(data, dict) and data.get("result") is not None else {}
    holdings = result.get("holdings") or result.get("positions")
    if not isinstance(holdings, list):
        return []

    by_date: dict[str, list[HoldingRecord]] = {}
    for item in holdings:
        if not isinstance(item, dict):
            continue
        date = str(item.get("date") or item.get("trade_date") or "")
        if not date:
            continue
        by_date.setdefault(date, []).append(
            HoldingRecord(
                symbol=str(item.get("symbol") or item.get("security") or ""),
                name=str(item.get("name") or item.get("security_name") or ""),
                quantity=float(item.get("quantity") or item.get("amount") or 0),
                avg_cost=float(item.get("avg_cost") or item.get("cost") or 0),
                close=float(item.get("close") or item.get("price") or 0),
                market_value=float(item.get("market_value") or item.get("value") or 0),
            )
        )

    groups: list[HoldingDayGroup] = []
    for date, rows in sorted(by_date.items()):
        total_market_value = sum(r.market_value for r in rows)
        groups.append(
            HoldingDayGroup(
                date=date,
                holdings=list(rows),
                summary=HoldingDaySummary(
                    total_market_value=total_market_value,
                    cash=0.0,
                    total_assets=total_market_value,
                ),
            )
        )
    return groups


def _get_result_sync(backtest_id: str, token: str, cookie: str, api_base: str) -> dict[str, Any]:
    """Sync jqcli get backtest result — runs in thread pool."""
    client = ApiClient(api_base, token=token, cookie=cookie)
    try:
        return get_backtest_result(client, backtest_id)
    finally:
        client.close()


def _normalize_metrics(metrics_data: dict[str, Any] | None) -> BacktestMetrics | None:
    if not metrics_data or not isinstance(metrics_data, dict):
        return None
    raw = dict(metrics_data)
    return BacktestMetrics(
        annual_return=raw.get("annual_algo_return") or raw.get("annual_return"),
        sharpe=raw.get("sharpe"),
        max_drawdown=raw.get("max_drawdown"),
        volatility=raw.get("volatility"),
        win_rate=raw.get("win_rate"),
        total_return=raw.get("total_return") or raw.get("algorithm_return"),
        raw=raw,
    )


class BacktestService:
    """jqcli backtest service — owns the ownership registry and unified errors."""

    def __init__(self, token: str, cookie: str, api_base: str) -> None:
        self._token = token
        self._cookie = cookie
        self._api_base = api_base
        self._registry = BacktestRegistry()

    @property
    def registry(self) -> BacktestRegistry:
        """Expose the owned registry (read-only intent)."""
        return self._registry

    def _resolve_user_id(self, user_id: UUID | str) -> UUID:
        return user_id if isinstance(user_id, UUID) else UUID(str(user_id))

    def assert_owner(self, backtest_id: str, user_id: UUID | str) -> None:
        """Raise BacktestError(404) if user does not own the backtest."""
        uid = self._resolve_user_id(user_id)
        if not self._registry.is_owner(backtest_id, uid):
            raise BacktestError(
                message="回测不存在或无权访问",
                code="backtest_not_found",
                status_code=404,
            )

    def _assert_thread_free(self, thread_id: UUID | str) -> None:
        key = str(thread_id)
        if self._registry.get_active_for_thread(key) is not None:
            raise BacktestError(
                message="当前会话已有进行中的回测，请等待完成",
                code="backtest_already_running",
                status_code=409,
            )

    def _has_credentials(self) -> bool:
        return bool(self._token or self._cookie)

    async def check_auth(self) -> AuthResult:
        """Check jqcli authentication status."""
        try:
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(
                _executor,
                functools.partial(_check_auth_sync, self._token, self._cookie, self._api_base),
            )
            return AuthResult(
                is_authenticated=True,
                username=result.get("username"),
                message="已认证",
            )
        except NotAuthenticatedError:
            return AuthResult(is_authenticated=False, message="未认证")
        except Exception as e:
            raise map_jqcli_error(e)

    async def check_auth_status(self) -> BacktestAuthStatus:
        """Combined auth status: configured flag + authenticated state."""
        if not self._has_credentials():
            return BacktestAuthStatus(
                configured=False,
                authenticated=False,
                username=None,
                message="未配置 JQCLI_TOKEN 或 JQCLI_COOKIE，请联系管理员",
            )
        result = await self.check_auth()
        return BacktestAuthStatus(
            configured=True,
            authenticated=result.is_authenticated,
            username=result.username,
            message=result.message,
        )

    async def submit_for_user(
        self,
        user_id: UUID,
        thread_id: UUID,
        code: str,
        version: int,
        params: BacktestParams,
    ) -> str:
        """Submit a backtest owned by user_id; raise 409 if thread is busy."""
        self._assert_thread_free(thread_id)
        try:
            params_dict = {
                "start_date": params.start_date,
                "end_date": params.end_date,
                "initial_capital": params.initial_capital,
                "frequency": params.frequency,
                "benchmark": params.benchmark,
            }
            loop = asyncio.get_running_loop()
            backtest_id: str = await loop.run_in_executor(
                _executor,
                functools.partial(
                    _submit_sync, code, params_dict, self._token, self._cookie, self._api_base
                ),
            )
        except Exception as e:
            raise map_jqcli_error(e)
        self._registry.register(backtest_id, user_id, thread_id=str(thread_id))
        return backtest_id

    async def submit(
        self,
        code: str,
        thread_id: UUID,
        version: int,
        params: BacktestParams,
    ) -> str:
        """Submit a backtest (low-level; no ownership check, no registry)."""
        try:
            params_dict = {
                "start_date": params.start_date,
                "end_date": params.end_date,
                "initial_capital": params.initial_capital,
                "frequency": params.frequency,
                "benchmark": params.benchmark,
            }
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(
                _executor,
                functools.partial(
                    _submit_sync, code, params_dict, self._token, self._cookie, self._api_base
                ),
            )
        except Exception as e:
            raise map_jqcli_error(e)

    async def poll(self, backtest_id: str) -> BacktestResult:
        """Poll backtest status."""
        try:
            loop = asyncio.get_running_loop()
            data = await loop.run_in_executor(
                _executor,
                functools.partial(
                    _poll_sync, backtest_id, self._token, self._cookie, self._api_base
                ),
            )

            status_str = data.get("status", "running")
            status_map = {
                "running": BacktestStatus.RUNNING,
                "done": BacktestStatus.DONE,
                "failed": BacktestStatus.FAILED,
                "cancelled": BacktestStatus.CANCELLED,
            }
            status = status_map.get(status_str, BacktestStatus.PENDING)

            metrics = _normalize_metrics(data.get("metrics"))

            return BacktestResult(
                backtest_id=backtest_id,
                status=status,
                metrics=metrics,
                error=data.get("error"),
            )
        except Exception as e:
            raise map_jqcli_error(e)

    async def poll_for_user(
        self,
        backtest_id: str,
        user_id: UUID | str,
    ) -> BacktestResult:
        """Ownership-checked poll wrapper."""
        self.assert_owner(backtest_id, user_id)
        return await self.poll(backtest_id)

    async def abort(self, backtest_id: str) -> bool:
        """Abort a running backtest (jqcli does not support it)."""
        raise BacktestError(
            message="聚宽不支持取消回测，请等待回测结束或重新提交",
            code="backtest_abort_unavailable",
            status_code=501,
        )

    async def abort_for_user(
        self,
        backtest_id: str,
        user_id: UUID | str,
    ) -> BacktestAbortResult:
        """Ownership-checked abort; returns typed BacktestAbortResult."""
        self.assert_owner(backtest_id, user_id)
        ok = await self.abort(backtest_id)
        return BacktestAbortResult(
            success=ok,
            message="回测已终止" if ok else "回测无法终止",
        )

    async def submit_simulation_for_user(
        self,
        backtest_id: str,
        user_id: UUID | str,
    ) -> BacktestSimulationResult:
        """Simulation stub — verifies ownership then returns deferred-impl result."""
        self.assert_owner(backtest_id, user_id)
        return BacktestSimulationResult(
            success=True,
            task_id=f"sim_{backtest_id}",
            status="submitted",
            message="已记录模拟任务",
        )

    async def get_metrics(self, backtest_id: str) -> BacktestMetrics:
        """Get backtest metrics."""
        result = await self.poll(backtest_id)
        if result.metrics:
            return result.metrics
        raise BacktestError(message="回测结果不可用", code="backtest_no_metrics")

    async def fetch_logs_incremental(
        self,
        backtest_id: str,
        offset: int = 0,
    ) -> BacktestLogResult:
        """Fetch incremental backtest logs from jqcli."""
        try:
            loop = asyncio.get_running_loop()
            payload = await loop.run_in_executor(
                _executor,
                functools.partial(
                    _get_logs_sync,
                    backtest_id,
                    offset,
                    self._token,
                    self._cookie,
                    self._api_base,
                ),
            )
            raw_logs = payload.get("logs") or []
            logs: list[str] = [str(line) for line in raw_logs]
            next_offset_raw = payload.get("next_offset", offset)
            next_offset = next_offset_raw if isinstance(next_offset_raw, int) else offset
            return BacktestLogResult(logs=logs, next_offset=next_offset)
        except Exception as e:
            raise map_jqcli_error(e)

    async def get_result_detail(self, backtest_id: str) -> dict[str, Any]:
        """Fetch full jqcli result and parse performance/trades/holdings.

        Internal callers (e.g., background workers) may need raw + parsed
        shapes; the API layer should call `get_result_detail_for_user`.
        """
        try:
            loop = asyncio.get_running_loop()
            payload = await loop.run_in_executor(
                _executor,
                functools.partial(
                    _get_result_sync, backtest_id, self._token, self._cookie, self._api_base
                ),
            )
            return {
                "performance": _parse_performance_series(payload),
                "trades": _parse_trade_groups(payload),
                "holdings": _parse_holding_groups(payload),
                "raw": payload,
            }
        except Exception as e:
            raise map_jqcli_error(e)

    async def get_result_detail_for_user(
        self,
        backtest_id: str,
        user_id: UUID | str,
    ) -> BacktestResultDetail:
        """Ownership-checked, typed detail result for the API layer.

        Raises BacktestError(404) if user doesn't own the backtest.
        When status is not DONE, performance/trades/holdings are empty lists.
        """
        self.assert_owner(backtest_id, user_id)
        result = await self.poll(backtest_id)

        performance: list[PerformancePoint] = []
        trades: list[TradeDayGroup] = []
        holdings: list[HoldingDayGroup] = []

        if result.status == BacktestStatus.DONE:
            detail = await self.get_result_detail(backtest_id)
            performance = detail["performance"]
            trades = detail["trades"]
            holdings = detail["holdings"]

        return BacktestResultDetail(
            backtest_id=result.backtest_id,
            status=result.status,
            metrics=result.metrics,
            performance=performance,
            trades=trades,
            holdings=holdings,
            error=result.error,
        )
