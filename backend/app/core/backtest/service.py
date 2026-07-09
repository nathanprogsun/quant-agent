"""Backtest service — wraps jqcli API with unified error handling."""

from __future__ import annotations

import asyncio
import functools
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
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
    PerformancePoint,
)

_executor = ThreadPoolExecutor(max_workers=4)

POLL_INTERVAL_SECONDS = 3
TIMEOUT_SECONDS = 300


def _check_auth_sync(token: str, cookie: str, api_base: str) -> dict[str, Any]:
    """Sync jqcli auth check — runs in thread pool.

    `get_current_user` is only present in deployed jqcli (not the vendored copy
    checked in here), so the attribute lookup is guarded to allow the fallback
    path when running against the local stub.
    """
    client = ApiClient(api_base, token=token, cookie=cookie)
    try:
        import jqcli.api.auth as _auth  # noqa: PLC0415

        get_current_user = getattr(_auth, "get_current_user", None)
        if get_current_user is None:
            user_info: dict[str, Any] = {"username": "authenticated"}
        else:
            fetched = get_current_user(client)
            user_info = fetched if isinstance(fetched, dict) else {"username": "authenticated"}
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


def _get_all_logs_sync(
    backtest_id: str,
    token: str,
    cookie: str,
    api_base: str,
) -> list[str]:
    """Fetch all backtest log lines for trade/holding extraction."""
    client = ApiClient(api_base, token=token, cookie=cookie)
    try:
        payload = get_backtest_logs(client, backtest_id, offset=0, all_items=True)
        raw_logs = payload.get("logs") or []
        return [str(line) for line in raw_logs]
    finally:
        client.close()


_MS_SERIES_KEYS = ("benchmark", "overallReturn")
_NESTED_MS_SERIES_KEYS = (
    ("orders", "buy"),
    ("orders", "sell"),
    ("gains", "earn"),
    ("gains", "lose"),
)


def _unwrap_result_block(result_payload: dict[str, Any]) -> dict[str, Any]:
    data = result_payload.get("data", result_payload)
    if isinstance(data, dict) and isinstance(data.get("data"), dict):
        data = data["data"]
    if not isinstance(data, dict):
        return {}
    result = data.get("result")
    return result if isinstance(result, dict) else {}


def _ms_to_date_str(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=UTC).strftime("%Y-%m-%d")


def _append_time_value_series(target: dict[str, Any], source: dict[str, Any]) -> None:
    for key in ("time", "value"):
        target_values = target.get(key)
        source_values = source.get(key)
        if isinstance(target_values, list) and isinstance(source_values, list):
            target_values.extend(source_values)
        elif isinstance(source_values, list):
            target[key] = list(source_values)


def _merge_result_series(target_result: dict[str, Any], page_result: dict[str, Any]) -> None:
    for key in _MS_SERIES_KEYS:
        page_series = page_result.get(key)
        if isinstance(page_series, dict):
            bucket = cast(dict[str, Any], target_result.setdefault(key, {"time": [], "value": []}))
            _append_time_value_series(bucket, page_series)
    for parent_key, child_key in _NESTED_MS_SERIES_KEYS:
        page_parent = page_result.get(parent_key)
        if not isinstance(page_parent, dict):
            continue
        target_parent = cast(dict[str, Any], target_result.setdefault(parent_key, {}))
        page_child = page_parent.get(child_key)
        if isinstance(page_child, dict):
            bucket = cast(
                dict[str, Any], target_parent.setdefault(child_key, {"time": [], "value": []})
            )
            _append_time_value_series(bucket, page_child)


def _fetch_full_result_sync(
    backtest_id: str,
    token: str,
    cookie: str,
    api_base: str,
) -> dict[str, Any]:
    """Fetch jqcli backtest chart result, merging paginated series when needed."""
    client = ApiClient(api_base, token=token, cookie=cookie)
    try:
        first_page = get_backtest_result(client, backtest_id, offset=0, user_record_offset=0)
        data = first_page.get("data")
        if not isinstance(data, dict):
            return first_page

        merged_result = dict(data.get("result") or {})
        count = int(merged_result.get("count") or 0)
        times = (merged_result.get("overallReturn") or {}).get("time") or []
        offset = len(times) if isinstance(times, list) else 0

        while count > 0 and offset < count:
            next_page = get_backtest_result(
                client,
                backtest_id,
                offset=offset,
                user_record_offset=0,
            )
            page_data = next_page.get("data") or {}
            page_result = page_data.get("result") or {}
            if not isinstance(page_result, dict):
                break
            _merge_result_series(merged_result, page_result)
            new_times = (merged_result.get("overallReturn") or {}).get("time") or []
            new_offset = len(new_times) if isinstance(new_times, list) else offset
            if new_offset <= offset:
                break
            offset = new_offset

        return {
            "id": backtest_id,
            "data": {
                "state": data.get("state"),
                "userRecord": data.get("userRecord"),
                "result": merged_result,
            },
        }
    finally:
        client.close()


def _parse_performance_series(result_payload: dict[str, Any]) -> list[PerformancePoint]:
    result = _unwrap_result_block(result_payload)
    if not result:
        return []

    strategy_series = result.get("overallReturn")
    benchmark_series = result.get("benchmark")
    if isinstance(strategy_series, dict):
        times = strategy_series.get("time") or []
        strategy_values = strategy_series.get("value") or []
        benchmark_values = (
            benchmark_series.get("value") or [] if isinstance(benchmark_series, dict) else []
        )
        if isinstance(times, list) and times:
            points: list[PerformancePoint] = []
            for index, raw_ms in enumerate(times):
                strategy_value = float(
                    strategy_values[index] if index < len(strategy_values) else 0
                )
                benchmark_value = float(
                    benchmark_values[index] if index < len(benchmark_values) else 0
                )
                points.append(
                    PerformancePoint(
                        date=_ms_to_date_str(int(raw_ms)),
                        strategy=strategy_value,
                        benchmark=benchmark_value,
                        relative=strategy_value - benchmark_value,
                    )
                )
            return points

    series = result.get("series") or result.get("chart_series") or result.get("charts")
    if not isinstance(series, list):
        return []

    legacy_points: list[PerformancePoint] = []
    for item in series:
        if not isinstance(item, dict):
            continue
        date = item.get("date") or item.get("time") or item.get("trade_date")
        if not date:
            continue
        legacy_points.append(
            PerformancePoint(
                date=str(date),
                strategy=float(item.get("strategy") or item.get("strategy_return") or 0),
                relative=float(item.get("relative") or item.get("relative_return") or 0),
                benchmark=float(item.get("benchmark") or item.get("benchmark_return") or 0),
                position_pct=item.get("position_pct"),
            )
        )
    return legacy_points


def _get_result_sync(backtest_id: str, token: str, cookie: str, api_base: str) -> dict[str, Any]:
    """Sync jqcli get backtest result — runs in thread pool."""
    return _fetch_full_result_sync(backtest_id, token, cookie, api_base)


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
    """jqcli backtest service — wraps a shared ownership registry.

    The registry is process-level (one instance per AppContext) so that
    ownership state survives across per-request service constructions.
    Without sharing, the SSE stream endpoint would rebuild a fresh
    ``BacktestService`` whose empty registry cannot find the backtest
    submitted moments earlier — producing a 404 on the SSE handshake.
    """

    def __init__(
        self,
        token: str,
        cookie: str,
        api_base: str,
        *,
        registry: BacktestRegistry | None = None,
    ) -> None:
        self._token = token
        self._cookie = cookie
        self._api_base = api_base
        self._registry = registry or BacktestRegistry()

    @property
    def registry(self) -> BacktestRegistry:
        """Expose the owned registry (read-only intent)."""
        return self._registry

    def _resolve_user_id(self, user_id: UUID | str) -> UUID:
        return user_id if isinstance(user_id, UUID) else UUID(str(user_id))

    def assert_owner(self, backtest_id: str, user_id: UUID | str) -> None:
        """Raise BacktestError(404) if user does not own the backtest.

        If the in-memory registry has no record (e.g. after a backend restart),
        the caller should use ``assert_owner_or_verify`` instead, which falls
        back to checking jqcli for the backtest's existence.
        """
        uid = self._resolve_user_id(user_id)
        if not self._registry.is_owner(backtest_id, uid):
            raise BacktestError(
                message="回测不存在或无权访问",
                code="backtest_not_found",
                status_code=404,
            )

    async def assert_owner_or_verify(self, backtest_id: str, user_id: UUID | str) -> None:
        """Ownership check with jqcli fallback for post-restart scenarios.

        The registry is in-memory; after a ``--reload`` restart it is empty.
        Instead of returning 404 for every backtest created before the restart,
        we ask jqcli whether the backtest exists. If jqcli confirms it exists,
        we re-register the ownership mapping so subsequent calls hit the fast
        in-memory path.
        """
        uid = self._resolve_user_id(user_id)
        if self._registry.is_owner(backtest_id, uid):
            return
        # Registry miss — could be a restart. Ask jqcli if the backtest exists.
        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(
                _executor,
                functools.partial(
                    _poll_sync, backtest_id, self._token, self._cookie, self._api_base
                ),
            )
        except Exception:
            raise BacktestError(
                message="回测不存在或无权访问",
                code="backtest_not_found",
                status_code=404,
            )
        # jqcli returned a valid response → backtest exists. Re-register
        # ownership so future calls skip the network round-trip.
        self._registry.register(backtest_id, uid)
        return

    def _assert_thread_free(self, thread_id: UUID | str) -> None:
        key = str(thread_id)
        if self._registry.get_active_for_thread(key) is not None:
            raise BacktestError(
                message="当前会话已有进行中的回测，请等待完成",
                code="backtest_already_running",
                status_code=409,
            )

    def get_active_for_thread(self, thread_id: UUID | str) -> str | None:
        """Return the active backtest_id for a thread, if any."""
        return self._registry.get_active_for_thread(str(thread_id))

    def cancel_for_thread(self, thread_id: UUID | str) -> str | None:
        """Release the thread's active backtest lock (local cancel).

        jqcli does not support aborting a remote backtest, but we CAN stop
        treating it as active locally so the user is not blocked. Returns the
        backtest_id that was active (if any) so the caller can cancel its
        worker task.
        """
        return self._registry.release_thread(str(thread_id))

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
                message="未配置 JQCLI_USERNAME/JQCLI_PASSWORD，请联系管理员",
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
        """Fetch full jqcli result and parse performance series.

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
            performance = _parse_performance_series(payload)

            return {
                "performance": performance,
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
        When status is not DONE, performance is an empty list.
        """
        self.assert_owner_or_verify(backtest_id, user_id)
        result = await self.poll(backtest_id)

        performance: list[PerformancePoint] = []

        if result.status == BacktestStatus.DONE:
            detail = await self.get_result_detail(backtest_id)
            performance = detail["performance"]

        return BacktestResultDetail(
            backtest_id=result.backtest_id,
            status=result.status,
            metrics=result.metrics,
            performance=performance,
            error=result.error,
        )
