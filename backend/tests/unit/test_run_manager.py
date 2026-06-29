"""Unit tests for RunManager."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.common.runs.manager import (
    ConflictError,
    RunManager,
    RunRecord,
)
from app.common.runs.schemas import RunStatus


@pytest.fixture
def manager() -> RunManager:
    return RunManager()


async def test_create_run(manager: RunManager) -> None:
    """create() returns a RunRecord with correct fields."""
    thread_id = uuid4()
    user_id = uuid4()
    record = await manager.create(thread_id, user_id, model_name="gpt-4o")
    assert record.thread_id == thread_id
    assert record.user_id == user_id
    assert record.model_name == "gpt-4o"
    assert record.status == RunStatus.PENDING


async def test_ttl_expiration(manager: RunManager) -> None:
    """Expired records are evicted on next create()."""
    record = await manager.create(uuid4(), uuid4())

    # Backdate updated_at beyond TTL
    past = (datetime.now(UTC) - timedelta(seconds=manager.RUN_TTL_SECONDS + 10)).isoformat()
    record.updated_at = past

    # Trigger eviction
    await manager.create(uuid4(), uuid4())

    assert await manager.get(record.run_id) is None


async def test_lru_eviction(manager: RunManager) -> None:
    """Oldest record evicted when MAX_RUNS exceeded."""
    manager.MAX_RUNS = 3

    r1 = await manager.create(uuid4(), uuid4())
    r2 = await manager.create(uuid4(), uuid4())
    _r3 = await manager.create(uuid4(), uuid4())
    # Backdate r1 to ensure it's clearly the oldest
    r1.updated_at = "1979-01-01T00:00:00+00:00"

    r4 = await manager.create(uuid4(), uuid4())  # triggers eviction

    # r1 is oldest, should be evicted
    assert await manager.get(r1.run_id) is None
    assert await manager.get(r2.run_id) is not None
    assert await manager.get(r4.run_id) is not None


async def test_create_or_reject_conflict(manager: RunManager) -> None:
    """reject strategy raises ConflictError on inflight run."""
    thread_id = uuid4()
    user_id = uuid4()
    await manager.create_or_reject(thread_id, user_id)

    with pytest.raises(ConflictError):
        await manager.create_or_reject(thread_id, user_id, multitask_strategy="reject")


async def test_create_or_reject_interrupt(manager: RunManager) -> None:
    """interrupt strategy cancels inflight run and creates new one."""
    thread_id = uuid4()
    user_id = uuid4()
    r1 = await manager.create_or_reject(thread_id, user_id)
    r2 = await manager.create_or_reject(thread_id, user_id, multitask_strategy="interrupt")

    interrupted = await manager.get(r1.run_id)
    assert interrupted is not None
    assert interrupted.status == RunStatus.INTERRUPTED
    assert r2.status == RunStatus.PENDING


async def test_cancel(manager: RunManager) -> None:
    """cancel() sets abort_event and updates status."""
    record = await manager.create(uuid4(), uuid4())

    result = await manager.cancel(record.run_id)
    assert result is True
    assert record.abort_event.is_set()
    assert record.status == RunStatus.INTERRUPTED

    # Idempotent — cancelling again returns False (already interrupted)
    assert await manager.cancel(record.run_id) is False


async def test_set_status(manager: RunManager) -> None:
    """set_status updates record in-memory."""
    record = await manager.create(uuid4(), uuid4())
    await manager.set_status(record.run_id, RunStatus.RUNNING)

    updated = await manager.get(record.run_id)
    assert updated is not None
    assert updated.status == RunStatus.RUNNING


async def test_concurrent_create_or_reject(manager: RunManager) -> None:
    """Concurrent create_or_reject on same thread — only one succeeds."""
    thread_id = uuid4()
    user_id = uuid4()
    results = await asyncio.gather(
        manager.create_or_reject(thread_id, user_id),
        manager.create_or_reject(thread_id, user_id),
        return_exceptions=True,
    )

    successes = [r for r in results if isinstance(r, RunRecord)]
    conflicts = [r for r in results if isinstance(r, ConflictError)]

    assert len(successes) == 1
    assert len(conflicts) == 1
