"""RunManager — run lifecycle management with TTL + LRU eviction."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from app.common.runs.schemas import DisconnectMode, RunStatus

logger = logging.getLogger(__name__)


class MultitaskStrategy(StrEnum):
    REJECT = "reject"
    INTERRUPT = "interrupt"
    ROLLBACK = "rollback"
    ENQUEUE = "enqueue"


MULTITASK_STRATEGIES = tuple(s.value for s in MultitaskStrategy)


@dataclass
class RunRecord:
    """Run record — mutable by design.

    RunRecord is a long-lived in-memory state object. Fields like
    abort_event and task must be modified in-place for cross-coroutine
    cancellation signaling. Known exemption from Immutability principle.
    """

    run_id: UUID
    thread_id: UUID
    user_id: UUID
    status: RunStatus = RunStatus.PENDING
    model_name: str | None = None
    assistant_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    on_disconnect: DisconnectMode = DisconnectMode.CANCEL
    multitask_strategy: str = "reject"
    task: asyncio.Task[None] | None = None
    abort_event: asyncio.Event = field(default_factory=asyncio.Event)
    abort_action: str = "interrupt"
    error: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


class ConflictError(Exception):
    """Raised when multitask_strategy=reject and thread has inflight runs."""


class UnsupportedStrategyError(Exception):
    """Raised for unknown multitask_strategy values."""


class RunStore:
    """Run persistence abstraction.

    Phase 1: NoopRunStore (in-memory only, no persistence).
    Phase 2+: SqlRunStore (persist to runs table).
    """

    async def save(self, record: RunRecord) -> None:
        pass

    async def load(self, run_id: UUID) -> RunRecord | None:
        return None

    async def list_by_thread(self, thread_id: UUID) -> list[RunRecord]:
        return []


class RunManager:
    """Run lifecycle manager with TTL expiration and LRU eviction.

    - In-memory registry with asyncio.Lock for thread safety
    - TTL auto-expiry + LRU eviction to prevent unbounded memory growth
    - Supports multitask_strategy: reject / interrupt / rollback / enqueue
    - Optional RunStore persistence
    """

    MAX_RUNS: int = 1000
    RUN_TTL_SECONDS: int = 3600

    def __init__(self, store: RunStore | None = None) -> None:
        self._runs: dict[UUID, RunRecord] = {}
        self._lock = asyncio.Lock()
        self._store = store or RunStore()

    async def _evict_expired(self) -> None:
        """Clean up expired + over-limit RunRecords.

        Runs opportunistically on each create() call — no timer needed.
        """
        now = datetime.now(UTC)
        expired = [
            run_id
            for run_id, record in self._runs.items()
            if (now - datetime.fromisoformat(record.updated_at)).total_seconds()
            > self.RUN_TTL_SECONDS
        ]
        for run_id in expired:
            self._runs.pop(run_id, None)

        # LRU eviction: drop oldest by updated_at when over limit
        while len(self._runs) > self.MAX_RUNS:
            oldest = min(self._runs, key=lambda rid: self._runs[rid].updated_at)
            self._runs.pop(oldest, None)

    async def create(
        self,
        thread_id: UUID,
        user_id: UUID,
        *,
        model_name: str | None = None,
        assistant_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        on_disconnect: DisconnectMode = DisconnectMode.CANCEL,
        multitask_strategy: str = "reject",
    ) -> RunRecord:
        async with self._lock:
            await self._evict_expired()
            run_id = uuid4()
            record = RunRecord(
                run_id=run_id,
                thread_id=thread_id,
                user_id=user_id,
                model_name=model_name,
                assistant_id=assistant_id,
                metadata=metadata or {},
                on_disconnect=on_disconnect,
                multitask_strategy=multitask_strategy,
            )
            self._runs[run_id] = record
            await self._store.save(record)
            return record

    async def get(self, run_id: UUID) -> RunRecord | None:
        async with self._lock:
            return self._runs.get(run_id)

    async def list_by_thread(self, thread_id: UUID) -> list[RunRecord]:
        async with self._lock:
            return sorted(
                [r for r in self._runs.values() if r.thread_id == thread_id],
                key=lambda r: r.created_at,
                reverse=True,
            )

    async def set_status(self, run_id: UUID, status: RunStatus, *, error: str | None = None) -> None:
        record_to_save = None
        async with self._lock:
            record = self._runs.get(run_id)
            if record:
                record.status = status
                record.error = error
                record.updated_at = datetime.now(UTC).isoformat()
                record_to_save = record
        # Persist outside lock to avoid unbounded lock hold time
        if record_to_save:
            await self._store.save(record_to_save)

    async def cancel(self, run_id: UUID, *, action: str = "interrupt") -> bool:
        """Cancel a run — idempotent, all mutations inside lock."""
        async with self._lock:
            record = self._runs.get(run_id)
            if not record:
                return False
            if record.status not in (RunStatus.PENDING, RunStatus.RUNNING):
                return False
            record.abort_event.set()
            record.abort_action = action
            if record.task and not record.task.done():
                record.task.cancel()
            record.status = RunStatus.INTERRUPTED
            record.updated_at = datetime.now(UTC).isoformat()
            await self._store.save(record)
        return True

    async def has_inflight(self, thread_id: UUID) -> bool:
        async with self._lock:
            return any(
                r.thread_id == thread_id and r.status in (RunStatus.PENDING, RunStatus.RUNNING)
                for r in self._runs.values()
            )

    async def create_or_reject(
        self,
        thread_id: UUID,
        user_id: UUID,
        **kwargs: Any,
    ) -> RunRecord:
        """Atomic check + create — prevents concurrent requests from
        inserting multiple inflight runs for the same thread.
        """
        strategy = kwargs.get("multitask_strategy", "reject")

        if strategy not in MULTITASK_STRATEGIES:
            raise UnsupportedStrategyError(f"Unknown strategy: {strategy}")

        async with self._lock:
            inflight = [
                r
                for r in self._runs.values()
                if r.thread_id == thread_id and r.status in (RunStatus.PENDING, RunStatus.RUNNING)
            ]

            if inflight:
                if strategy == "reject":
                    raise ConflictError(f"Thread {thread_id} has {len(inflight)} inflight run(s)")
                if strategy in ("interrupt", "rollback"):
                    for r in inflight:
                        r.abort_event.set()
                        r.abort_action = strategy
                        if r.task and not r.task.done():
                            r.task.cancel()
                        r.status = RunStatus.INTERRUPTED

            return self._create_internal(thread_id, user_id, **kwargs)

    def _create_internal(self, thread_id: UUID, user_id: UUID, **kwargs: Any) -> RunRecord:
        """Create RunRecord inside lock (caller must hold lock)."""
        record = RunRecord(
            run_id=uuid4(),
            thread_id=thread_id,
            user_id=user_id,
            multitask_strategy=kwargs.get("multitask_strategy", "reject"),
            on_disconnect=kwargs.get("on_disconnect", DisconnectMode.CANCEL),
            metadata=kwargs.get("metadata", {}),
        )
        self._runs[record.run_id] = record
        return record

    async def update_model_name(self, run_id: UUID, model_name: str) -> None:
        """Record the actual model name used by the agent."""
        async with self._lock:
            record = self._runs.get(run_id)
            if record:
                record.model_name = model_name
                await self._store.save(record)

    async def update_run_completion(self, run_id: UUID, **kwargs: Any) -> None:
        """Persist completion data: token usage, etc."""
        async with self._lock:
            record = self._runs.get(run_id)
            if record:
                record.metadata.update(kwargs)
                await self._store.save(record)

    async def cleanup(self, run_id: UUID, *, delay: float = 300) -> None:
        if delay > 0:
            await asyncio.sleep(delay)
        async with self._lock:
            self._runs.pop(run_id, None)
