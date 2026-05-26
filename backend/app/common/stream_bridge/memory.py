"""MemoryStreamBridge — in-memory implementation of StreamBridge."""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from app.common.stream_bridge.base import (
    END_SENTINEL,
    HEARTBEAT_SENTINEL,
    StreamBridge,
    StreamEvent,
)


@dataclass
class _RunStream:
    """Per-run event buffer."""

    events: list[StreamEvent] = field(default_factory=list)
    condition: asyncio.Condition = field(default_factory=asyncio.Condition)
    ended: bool = False
    start_offset: int = 0


class MemoryStreamBridge(StreamBridge):
    """In-memory StreamBridge with bounded buffer and reconnection support.

    Features:
    - Ring eviction when buffer exceeds maxsize
    - asyncio.Condition for subscriber notification
    - Reconnection via event replay from buffer
    - Heartbeat timeout

    Constraints:
    - Single-process deployment only (workers=1)
    - All publish/subscribe calls must be in the same event loop
    """

    def __init__(self, *, queue_maxsize: int = 256) -> None:
        self._streams: dict[str, _RunStream] = {}
        self._counters: dict[str, int] = {}
        self._maxsize = queue_maxsize

    def _next_id(self, run_id: str) -> str:
        ts = int(time.time() * 1000)
        seq = self._counters.get(run_id, 0) + 1
        self._counters[run_id] = seq
        return f"{ts}-{seq}"

    def _resolve_start_offset(
        self, stream: _RunStream, last_event_id: str | None
    ) -> int:
        """Locate replay start position for reconnection.

        Handles ring eviction: if last_event_id was evicted, start from
        the beginning of the current buffer.
        """
        if not last_event_id or not stream.events:
            return 0
        for i, evt in enumerate(stream.events):
            if evt.id == last_event_id:
                return i + 1
        return 0

    async def publish(self, run_id: str, event: str, data: Any) -> None:
        if run_id not in self._streams:
            self._streams[run_id] = _RunStream(start_offset=0)

        stream = self._streams[run_id]
        evt = StreamEvent(id=self._next_id(run_id), event=event, data=data)

        async with stream.condition:
            stream.events.append(evt)
            # Ring eviction
            if len(stream.events) > self._maxsize:
                overflow = len(stream.events) - self._maxsize
                stream.events = stream.events[overflow:]
                stream.start_offset += overflow
            stream.condition.notify_all()

    async def publish_end(self, run_id: str) -> None:
        stream = self._streams.get(run_id)
        if not stream:
            stream = _RunStream(start_offset=0)
            self._streams[run_id] = stream
        async with stream.condition:
            stream.ended = True
            stream.condition.notify_all()

    async def subscribe(
        self,
        run_id: str,
        *,
        last_event_id: str | None = None,
        heartbeat_interval: float = 15.0,
    ) -> AsyncIterator[StreamEvent]:
        stream = self._streams.get(run_id)
        if not stream:
            stream = _RunStream(start_offset=0)
            self._streams[run_id] = stream

        idx = self._resolve_start_offset(stream, last_event_id)

        while True:
            while idx < len(stream.events):
                yield stream.events[idx]
                idx += 1

            if stream.ended:
                yield END_SENTINEL
                return

            async with stream.condition:
                try:
                    await asyncio.wait_for(
                        stream.condition.wait(),
                        timeout=heartbeat_interval,
                    )
                except TimeoutError:
                    yield HEARTBEAT_SENTINEL

    async def cleanup(self, run_id: str, *, delay: float = 0) -> None:
        if delay > 0:
            await asyncio.sleep(delay)
        self._streams.pop(run_id, None)
        self._counters.pop(run_id, None)

    async def close(self) -> None:
        self._streams.clear()
        self._counters.clear()
