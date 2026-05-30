"""RunEventStore — event persistence for message and event history."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class RunEventStore(ABC):
    """Abstract base for run event persistence."""

    @abstractmethod
    async def list_messages(
        self,
        thread_id: str,
        limit: int = 50,
        before_seq: int | None = None,
        after_seq: int | None = None,
    ) -> list[dict[str, Any]]:
        """List messages for a thread with optional pagination."""
        ...

    @abstractmethod
    async def list_messages_by_run(
        self,
        thread_id: str,
        run_id: str,
        limit: int = 50,
        before_seq: int | None = None,
        after_seq: int | None = None,
    ) -> list[dict[str, Any]]:
        """List messages for a specific run with optional pagination."""
        ...

    @abstractmethod
    async def list_events(
        self,
        thread_id: str,
        run_id: str,
        event_types: list[str] | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """List events for a run, optionally filtered by type."""
        ...


class InMemoryEventStore(RunEventStore):
    """In-memory event store for development/testing."""

    def __init__(self) -> None:
        self._messages: dict[str, list[dict]] = {}
        self._events: dict[str, list[dict]] = {}

    async def list_messages(
        self,
        thread_id: str,
        limit: int = 50,
        before_seq: int | None = None,
        after_seq: int | None = None,
    ) -> list[dict[str, Any]]:
        messages = self._messages.get(thread_id, [])
        if before_seq is not None:
            messages = [m for m in messages if m.get("seq", 0) < before_seq]
        if after_seq is not None:
            messages = [m for m in messages if m.get("seq", 0) > after_seq]
        return messages[-limit:]

    async def list_messages_by_run(
        self,
        thread_id: str,
        run_id: str,
        limit: int = 50,
        before_seq: int | None = None,
        after_seq: int | None = None,
    ) -> list[dict[str, Any]]:
        messages = [
            m for m in self._messages.get(thread_id, [])
            if m.get("run_id") == run_id
        ]
        if before_seq is not None:
            messages = [m for m in messages if m.get("seq", 0) < before_seq]
        if after_seq is not None:
            messages = [m for m in messages if m.get("seq", 0) > after_seq]
        return messages[-limit:]

    async def list_events(
        self,
        thread_id: str,
        run_id: str,
        event_types: list[str] | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        key = f"{thread_id}:{run_id}"
        events = self._events.get(key, [])
        if event_types:
            events = [e for e in events if e.get("event") in event_types]
        return events[:limit]
