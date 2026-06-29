"""StreamBridge ABC + StreamEvent — SSE event pub/sub abstraction."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any
from uuid import UUID


@dataclass(frozen=True)
class StreamEvent:
    """Immutable SSE event."""

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

    Producers publish() and consumers subscribe() with Last-Event-ID replay.
    Single-process only (workers=1).
    """

    @abstractmethod
    async def publish(self, run_id: UUID, event: str, data: Any) -> None:
        """Publish an event for a run."""

    @abstractmethod
    async def publish_end(self, run_id: UUID) -> None:
        """Signal that a run has finished."""

    @abstractmethod
    def subscribe(
        self,
        run_id: UUID,
        *,
        last_event_id: str | None = None,
        heartbeat_interval: float = 15.0,
    ) -> AsyncIterator[StreamEvent]:
        """Subscribe to a run's event stream with reconnection support."""

    @abstractmethod
    async def cleanup(self, run_id: UUID, *, delay: float = 0) -> None:
        """Delayed cleanup of run resources."""

    async def close(self) -> None:
        """Release all resources."""
