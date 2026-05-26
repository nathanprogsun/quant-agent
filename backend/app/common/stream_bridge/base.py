"""StreamBridge ABC + StreamEvent — SSE event pub/sub abstraction."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class StreamEvent:
    """Immutable SSE event.

    Attributes:
        id: Monotonic event ID ("{timestamp_ms}-{seq}").
        event: Event type (metadata | messages | values | updates | custom | error | end).
        data: JSON-serializable payload.
    """

    id: str
    event: str
    data: Any


HEARTBEAT_SENTINEL = StreamEvent(id="", event="__heartbeat__", data=None)
END_SENTINEL = StreamEvent(id="", event="__end__", data=None)

# Connection limits
MAX_CONCURRENT_STREAMS = 500
MAX_SSE_CONNECTIONS_PER_USER = 5
SSE_MAX_LIFETIME_SECONDS = 1800


class StreamBridge(ABC):
    """SSE event pub/sub abstraction.

    Producers call publish() to emit events; consumers call subscribe()
    to receive an async stream of events. Supports reconnection via
    Last-Event-ID replay.

    Constraint: single-process only (workers=1). Multi-process deployments
    require a Redis-backed implementation.
    """

    @abstractmethod
    async def publish(self, run_id: str, event: str, data: Any) -> None:
        """Publish an event for a run."""

    @abstractmethod
    async def publish_end(self, run_id: str) -> None:
        """Signal that a run has finished."""

    @abstractmethod
    def subscribe(
        self,
        run_id: str,
        *,
        last_event_id: str | None = None,
        heartbeat_interval: float = 15.0,
    ) -> AsyncIterator[StreamEvent]:
        """Subscribe to a run's event stream with reconnection support."""

    @abstractmethod
    async def cleanup(self, run_id: str, *, delay: float = 0) -> None:
        """Delayed cleanup of run resources."""

    async def close(self) -> None:
        """Release all resources."""
