"""Background backtest polling worker — publishes StreamBridge SSE events."""

from __future__ import annotations

import asyncio
import logging
from typing import Any
from uuid import UUID

from app.common.stream_bridge.base import StreamBridge
from app.core.backtest.errors import BacktestError
from app.core.backtest.service import POLL_INTERVAL_SECONDS, TIMEOUT_SECONDS, BacktestService
from app.core.backtest.types import BacktestStatus

logger = logging.getLogger(__name__)


async def _publish_event(bridge: StreamBridge, run_id: UUID, payload: dict[str, Any]) -> None:
    """Publish a backtest event consumable by EventSource.onmessage."""
    await bridge.publish(run_id, "message", payload)


async def run_backtest_worker(
    *,
    bridge: StreamBridge,
    service: BacktestService,
    backtest_id: str,
    run_id: UUID,
) -> None:
    """Poll jqcli until terminal state and publish SSE events every 3s."""
    elapsed = 0.0
    log_offset = 0
    try:
        await _publish_event(
            bridge,
            run_id,
            {"type": "backtest_started", "backtest_id": backtest_id},
        )

        while elapsed < TIMEOUT_SECONDS:
            result = await service.poll(backtest_id)

            if result.status == BacktestStatus.RUNNING:
                try:
                    logs_payload = await service.fetch_logs_incremental(
                        backtest_id, log_offset
                    )
                    for line in logs_payload.get("logs", []):
                        await _publish_event(
                            bridge,
                            run_id,
                            {
                                "type": "backtest_log_line",
                                "backtest_id": backtest_id,
                                "line": str(line),
                            },
                        )
                    next_offset = logs_payload.get("next_offset")
                    if isinstance(next_offset, int):
                        log_offset = next_offset
                except Exception:
                    logger.debug("Log fetch skipped for %s", backtest_id)

                await _publish_event(
                    bridge,
                    run_id,
                    {
                        "type": "backtest_progress",
                        "backtest_id": backtest_id,
                        "message": "回测进行中...",
                    },
                )
                await asyncio.sleep(POLL_INTERVAL_SECONDS)
                elapsed += POLL_INTERVAL_SECONDS
                continue

            if result.status == BacktestStatus.DONE:
                metrics_payload = None
                if result.metrics:
                    raw = result.metrics.raw or {}
                    metrics_payload = {
                        "annual_return": result.metrics.annual_return,
                        "sharpe": result.metrics.sharpe,
                        "max_drawdown": result.metrics.max_drawdown,
                        "volatility": result.metrics.volatility,
                        "win_rate": result.metrics.win_rate,
                        "total_return": raw.get("total_return") or raw.get("algorithm_return"),
                    }
                await _publish_event(
                    bridge,
                    run_id,
                    {
                        "type": "backtest_completed",
                        "backtest_id": backtest_id,
                        "metrics": metrics_payload,
                    },
                )
                return

            if result.status == BacktestStatus.CANCELLED:
                await _publish_event(
                    bridge,
                    run_id,
                    {"type": "backtest_aborted", "backtest_id": backtest_id},
                )
                return

            error_msg = result.error or "回测失败"
            await _publish_event(
                bridge,
                run_id,
                {
                    "type": "backtest_failed",
                    "backtest_id": backtest_id,
                    "error": error_msg,
                },
            )
            return

        await _publish_event(
            bridge,
            run_id,
            {
                "type": "backtest_failed",
                "backtest_id": backtest_id,
                "error": "回测超时",
            },
        )
    except BacktestError as exc:
        await _publish_event(
            bridge,
            run_id,
            {
                "type": "backtest_failed",
                "backtest_id": backtest_id,
                "error": exc.message,
            },
        )
    except Exception:
        logger.exception("Backtest worker failed for %s", backtest_id)
        await _publish_event(
            bridge,
            run_id,
            {
                "type": "backtest_failed",
                "backtest_id": backtest_id,
                "error": "回测服务异常",
            },
        )
    finally:
        await bridge.publish_end(run_id)
        await bridge.cleanup(run_id, delay=60)
