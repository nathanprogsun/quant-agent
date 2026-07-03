"""MemoryStreamBridge — in-memory implementation of StreamBridge."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from app.common.stream_bridge.base import (
    END_SENTINEL,
    HEARTBEAT_SENTINEL,
    StreamBridge,
    StreamEvent,
)

logger = logging.getLogger(__name__)


@dataclass
class _RunStream:
    """Per-run event buffer."""

    events: list[StreamEvent] = field(default_factory=list)
    condition: asyncio.Condition = field(default_factory=asyncio.Condition)
    ended: bool = False
    # Absolute offset of events[0] in the run's event sequence. Increases
    # as ring eviction drops the oldest events from the buffer.
    start_offset: int = 0


class MemoryStreamBridge(StreamBridge):
    """In-memory StreamBridge with bounded buffer and reconnection support.

    Features:
    - Ring eviction when buffer exceeds maxsize
    - asyncio.Condition for subscriber notification
    - O(1) reconnection: event ids embed a per-run, monotonically increasing
      ``seq`` so the replay offset can be computed arithmetically instead of
      scanning the retained buffer. Stale / evicted / malformed
      ``last_event_id`` values fall back to replaying from the earliest
      retained event (never from offset 0, which may have been evicted).
    - Heartbeat timeout

    Constraints:
    - Single-process deployment only (workers=1)
    - All publish/subscribe calls must be in the same event loop
    """

    def __init__(self, *, queue_maxsize: int = 4096) -> None:
        self._streams: dict[UUID, _RunStream] = {}
        self._counters: dict[UUID, int] = {}
        self._maxsize = queue_maxsize

    def _next_id(self, run_id: UUID) -> str:
        """Assign the next event id, embedding the per-run ``seq``.

        Id format is ``{ts_ms}-{seq}`` where ``seq`` is 0-based and matches the
        event's absolute offset within the run (the first event has seq=0).
        This lets reconnection resolve the replay offset in O(1) via
        :meth:`_event_seq`, since ``seq`` equals ``start_offset + local_index``.
        """
        self._counters[run_id] = self._counters.get(run_id, 0) + 1
        ts = int(time.time() * 1000)
        seq = self._counters[run_id] - 1
        return f"{ts}-{seq}"

    @staticmethod
    def _event_seq(event_id: str) -> int | None:
        """Extract the embedded per-run ``seq`` from a ``{ts}-{seq}`` id.

        Returns ``None`` when the id does not match the expected shape, so
        callers can fall back to a buffer scan or to replay-from-earliest.
        """
        _, sep, seq_text = event_id.rpartition("-")
        if not sep:
            return None
        try:
            return int(seq_text)
        except ValueError:
            return None

    def _resolve_start_offset(self, stream: _RunStream, last_event_id: str | None) -> int:
        """Locate the replay start position for reconnection.

        Three paths, cheapest first:

        1. No ``last_event_id`` → start from the earliest retained event
           (``stream.start_offset``), which is correct even after ring
           eviction (it advances as old events drop out).
        2. ``last_event_id`` embeds a ``seq`` → arithmetic in O(1). The id
           is verified at the computed index so a stale / evicted / foreign /
           malformed id still falls back to replay-from-earliest.
        3. ``last_event_id`` has no parseable ``seq`` → linear scan of the
           retained buffer. Falls back to ``stream.start_offset`` when the
           id is not found, which replays the whole retained buffer (same
           behaviour as deer-flow's MemoryStreamBridge).
        """
        if last_event_id is None:
            return stream.start_offset

        seq = self._event_seq(last_event_id)
        if seq is not None:
            local_index = seq - stream.start_offset
            if (
                0 <= local_index < len(stream.events)
                and stream.events[local_index].id == last_event_id
            ):
                return stream.start_offset + local_index + 1
            # Stale / evicted / foreign id — fall through to scan, then
            # earliest-retained fallback.

        if stream.events:
            for i, evt in enumerate(stream.events):
                if evt.id == last_event_id:
                    return stream.start_offset + i + 1
            logger.warning(
                "last_event_id=%s not found in retained buffer; replaying from earliest retained event",
                last_event_id,
            )
        return stream.start_offset

    async def publish(self, run_id: UUID, event: str, data: Any) -> None:
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

    async def publish_end(self, run_id: UUID) -> None:
        stream = self._streams.get(run_id)
        if not stream:
            stream = _RunStream(start_offset=0)
            self._streams[run_id] = stream
        async with stream.condition:
            stream.ended = True
            stream.condition.notify_all()

    async def subscribe(
        self,
        run_id: UUID,
        *,
        last_event_id: str | None = None,
        heartbeat_interval: float = 15.0,
    ) -> AsyncIterator[StreamEvent]:
        stream = self._streams.get(run_id)
        if not stream:
            stream = _RunStream(start_offset=0)
            self._streams[run_id] = stream

        next_offset = self._resolve_start_offset(stream, last_event_id)

        while True:
            # Re-base the subscriber if it has fallen behind the retained
            # buffer (e.g. a long pause followed by ring eviction). Without
            # this guard, a stale next_offset below start_offset would index
            # into negative list positions and mask the eviction.
            if next_offset < stream.start_offset:
                logger.warning(
                    "subscriber for run %s fell behind retained buffer; resuming from offset %s",
                    run_id,
                    stream.start_offset,
                )
                next_offset = stream.start_offset

            local_index = next_offset - stream.start_offset
            if 0 <= local_index < len(stream.events):
                # Yield without holding the condition: the buffer is append-only
                # with ring eviction that only advances start_offset, so the
                # index remains valid for the duration of this yield.
                entry = stream.events[local_index]
                next_offset += 1
                yield entry
                continue

            if stream.ended:
                yield END_SENTINEL
                return

            async with stream.condition:
                # Re-check inside the lock to avoid the race where publish_end
                # notifies while we're between the flag check above and wait().
                if next_offset < stream.start_offset:
                    continue
                if local_index < len(stream.events):
                    continue
                try:
                    await asyncio.wait_for(
                        stream.condition.wait(),
                        timeout=heartbeat_interval,
                    )
                except TimeoutError:
                    yield HEARTBEAT_SENTINEL

    async def cleanup(self, run_id: UUID, *, delay: float = 0) -> None:
        if delay > 0:
            await asyncio.sleep(delay)
        self._streams.pop(run_id, None)
        self._counters.pop(run_id, None)

    async def close(self) -> None:
        self._streams.clear()
        self._counters.clear()
