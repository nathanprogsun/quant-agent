"""Backtest SSE streaming via StreamBridge."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from uuid import NAMESPACE_URL, UUID, uuid5

from fastapi import Request

from app.common.stream_bridge.base import StreamBridge

logger = logging.getLogger(__name__)


def backtest_stream_run_id(backtest_id: str) -> UUID:
    """Derive a stable StreamBridge run id from backtest id."""
    return uuid5(NAMESPACE_URL, f"backtest:{backtest_id}")


def format_backtest_sse(data: dict) -> str:
    """Format SSE frame for EventSource.onmessage (no named event)."""
    payload = json.dumps(data, ensure_ascii=False, default=str)
    return f"data: {payload}\n\n"


async def backtest_sse_consumer(
    bridge: StreamBridge,
    run_id: UUID,
    request: Request,
) -> AsyncIterator[str]:
    """Consume StreamBridge backtest events as SSE message frames."""
    last_event_id = request.headers.get("Last-Event-ID")
    try:
        async for event in bridge.subscribe(
            run_id,
            last_event_id=last_event_id,
            heartbeat_interval=15.0,
        ):
            if event.event == "__heartbeat__":
                yield ": heartbeat\n\n"
                continue

            if event.event == "__end__":
                break

            if event.event == "message" and isinstance(event.data, dict):
                yield format_backtest_sse(event.data)

    except asyncio.CancelledError:
        logger.info("Backtest SSE client disconnected for run %s", run_id)
