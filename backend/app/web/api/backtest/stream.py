"""Backtest SSE streaming via StreamBridge."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from uuid import NAMESPACE_URL, UUID, uuid5

from fastapi import Request

from app.common.stream_bridge.base import StreamBridge, StreamEvent

logger = logging.getLogger(__name__)


def backtest_stream_run_id(backtest_id: str) -> UUID:
    """Derive a stable StreamBridge run id from backtest id."""
    return uuid5(NAMESPACE_URL, f"backtest:{backtest_id}")


def format_backtest_sse(payload: dict[str, object]) -> str:
    """Format SSE frame for EventSource.onmessage (no named event).

    Payload is intentionally `dict` — the inner event shape is defined by the
    backtest worker (types: backtest_started, backtest_log_line,
    backtest_progress, backtest_completed, backtest_aborted, backtest_failed)
    and consumed by the JS EventSource listener as JSON.
    """
    encoded = json.dumps(payload, ensure_ascii=False, default=str)
    return f"data: {encoded}\n\n"


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
            if _is_heartbeat(event):
                yield ": heartbeat\n\n"
                continue

            if _is_end(event):
                break

            if _is_message_payload(event):
                yield format_backtest_sse(event.data)

    except asyncio.CancelledError:
        logger.info("Backtest SSE client disconnected for run %s", run_id)


def _is_heartbeat(event: StreamEvent) -> bool:
    return event.event == "__heartbeat__"


def _is_end(event: StreamEvent) -> bool:
    return event.event == "__end__"


def _is_message_payload(event: StreamEvent) -> bool:
    return event.event == "message" and isinstance(event.data, dict)
