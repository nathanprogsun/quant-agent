"""Backtest service — wraps jqcli API with unified error handling."""

from __future__ import annotations

import asyncio
import functools
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from uuid import UUID

from jqcli.errors import NotAuthenticatedError

from app.core.backtest.errors import BacktestError, map_jqcli_error
from app.core.backtest.types import (
    AuthResult,
    BacktestMetrics,
    BacktestParams,
    BacktestResult,
    BacktestStatus,
)

_executor = ThreadPoolExecutor(max_workers=4)

POLL_INTERVAL_SECONDS = 3
TIMEOUT_SECONDS = 300


def _check_auth_sync(token: str, cookie: str, api_base: str) -> dict[str, Any]:
    """Sync jqcli auth check — runs in thread pool."""
    from jqcli.api.auth import get_current_user
    from jqcli.api.client import ApiClient

    client = ApiClient(api_base, token=token, cookie=cookie)
    try:
        user_info = get_current_user(client)
        return {"username": user_info.get("username", "authenticated")}
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
    from jqcli.api.backtest import run_backtest
    from jqcli.api.client import ApiClient
    from jqcli.api.strategy import create_strategy

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
    from jqcli.api.backtest import get_backtest
    from jqcli.api.client import ApiClient

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
    from jqcli.api.backtest import get_backtest_logs
    from jqcli.api.client import ApiClient

    client = ApiClient(api_base, token=token, cookie=cookie)
    try:
        return get_backtest_logs(client, backtest_id, offset=offset, all_items=False)
    finally:
        client.close()


def _parse_performance_series(result_payload: dict[str, Any]) -> list[dict[str, Any]]:
    data = result_payload.get("data", result_payload)
    if isinstance(data, dict) and isinstance(data.get("data"), dict):
        data = data["data"]
    result = data.get("result") if isinstance(data, dict) else {}
    if not isinstance(result, dict):
        return []

    series = result.get("series") or result.get("chart_series") or result.get("charts")
    if not isinstance(series, list):
        return []

    points: list[dict[str, Any]] = []
    for item in series:
        if not isinstance(item, dict):
            continue
        date = item.get("date") or item.get("time") or item.get("trade_date")
        if not date:
            continue
        points.append(
            {
                "date": str(date),
                "strategy": float(item.get("strategy") or item.get("strategy_return") or 0),
                "relative": float(item.get("relative") or item.get("relative_return") or 0),
                "benchmark": float(item.get("benchmark") or item.get("benchmark_return") or 0),
                "position_pct": item.get("position_pct"),
            }
        )
    return points


def _parse_trade_groups(result_payload: dict[str, Any]) -> list[dict[str, Any]]:
    data = result_payload.get("data", result_payload)
    if isinstance(data, dict) and isinstance(data.get("data"), dict):
        data = data["data"]
    result = data.get("result") if isinstance(data, dict) else {}
    trades = result.get("trades") if isinstance(result, dict) else None
    if not isinstance(trades, list):
        return []

    by_date: dict[str, list[dict[str, Any]]] = {}
    for item in trades:
        if not isinstance(item, dict):
            continue
        date = str(item.get("date") or item.get("trade_date") or "")
        if not date:
            continue
        by_date.setdefault(date, []).append(
            {
                "symbol": str(item.get("symbol") or item.get("security") or ""),
                "name": str(item.get("name") or item.get("security_name") or ""),
                "side": str(item.get("side") or item.get("action") or ""),
                "quantity": float(item.get("quantity") or item.get("amount") or 0),
                "price": float(item.get("price") or 0),
            }
        )

    return [{"date": date, "trades": rows} for date, rows in sorted(by_date.items())]


def _parse_holding_groups(result_payload: dict[str, Any]) -> list[dict[str, Any]]:
    data = result_payload.get("data", result_payload)
    if isinstance(data, dict) and isinstance(data.get("data"), dict):
        data = data["data"]
    result = data.get("result") if isinstance(data, dict) else {}
    holdings = result.get("holdings") or result.get("positions")
    if not isinstance(holdings, list):
        return []

    by_date: dict[str, list[dict[str, Any]]] = {}
    for item in holdings:
        if not isinstance(item, dict):
            continue
        date = str(item.get("date") or item.get("trade_date") or "")
        if not date:
            continue
        by_date.setdefault(date, []).append(
            {
                "symbol": str(item.get("symbol") or item.get("security") or ""),
                "name": str(item.get("name") or item.get("security_name") or ""),
                "quantity": float(item.get("quantity") or item.get("amount") or 0),
                "avg_cost": float(item.get("avg_cost") or item.get("cost") or 0),
                "close": float(item.get("close") or item.get("price") or 0),
                "market_value": float(item.get("market_value") or item.get("value") or 0),
            }
        )

    groups: list[dict[str, Any]] = []
    for date, rows in sorted(by_date.items()):
        total_market_value = sum(r["market_value"] for r in rows)
        groups.append(
            {
                "date": date,
                "holdings": rows,
                "summary": {
                    "total_market_value": total_market_value,
                    "cash": 0.0,
                    "total_assets": total_market_value,
                },
            }
        )
    return groups


def _get_result_sync(backtest_id: str, token: str, cookie: str, api_base: str) -> dict[str, Any]:
    """Sync jqcli get backtest result — runs in thread pool."""
    from jqcli.api.backtest import get_backtest_result
    from jqcli.api.client import ApiClient

    client = ApiClient(api_base, token=token, cookie=cookie)
    try:
        return get_backtest_result(client, backtest_id)
    finally:
        client.close()


class BacktestService:
    """jqcli backtest service — process-internal with unified error handling."""

    def __init__(self, token: str, cookie: str, api_base: str) -> None:
        self._token = token
        self._cookie = cookie
        self._api_base = api_base

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

    async def submit(
        self,
        code: str,
        thread_id: UUID,
        version: int,
        params: BacktestParams,
    ) -> str:
        """Submit a backtest, return backtest_id."""
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
        """Poll backtest status until done/failed/cancelled."""
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

            metrics = None
            metrics_data = data.get("metrics")
            if metrics_data and isinstance(metrics_data, dict):
                metrics = BacktestMetrics(
                    annual_return=metrics_data.get("annual_algo_return") or metrics_data.get("annual_return"),
                    sharpe=metrics_data.get("sharpe"),
                    max_drawdown=metrics_data.get("max_drawdown"),
                    volatility=metrics_data.get("volatility"),
                    win_rate=metrics_data.get("win_rate"),
                    raw=metrics_data,
                )

            return BacktestResult(
                backtest_id=backtest_id,
                status=status,
                metrics=metrics,
                error=data.get("error"),
            )
        except Exception as e:
            raise map_jqcli_error(e)

    async def abort(self, backtest_id: str) -> bool:
        """Abort a running backtest."""
        raise BacktestError(
            message="聚宽不支持取消回测，请等待回测结束或重新提交",
            code="backtest_abort_unavailable",
            status_code=501,
        )

    async def get_metrics(self, backtest_id: str) -> BacktestMetrics:
        """Get backtest metrics."""
        result = await self.poll(backtest_id)
        if result.metrics:
            return result.metrics
        raise BacktestError(message="回测结果不可用", code="backtest_no_metrics")

    async def fetch_logs_incremental(self, backtest_id: str, offset: int = 0) -> dict[str, Any]:
        """Fetch incremental backtest logs from jqcli."""
        try:
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(
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
        except Exception as e:
            raise map_jqcli_error(e)

    async def get_result_detail(self, backtest_id: str) -> dict[str, Any]:
        """Fetch full jqcli result and parse performance/trades/holdings."""
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
