"""RunStore — persistence abstraction with SQLite implementation."""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any
from uuid import UUID

from app.common.runs.manager import PersistenceRetryPolicy
from app.common.runs.schemas import RunStatus

logger = logging.getLogger(__name__)


class RunStore(ABC):
    """Abstract base for run persistence."""

    @abstractmethod
    async def put(self, run_id: UUID, **kwargs) -> None:
        """Persist or update a run record."""
        ...

    @abstractmethod
    async def get(self, run_id: UUID, user_id: UUID | None = None) -> dict | None:
        """Load a run record by ID."""
        ...

    @abstractmethod
    async def list_by_thread(
        self, thread_id: UUID, user_id: UUID | None = None, limit: int = 100
    ) -> list[dict]:
        """List runs for a thread."""
        ...

    @abstractmethod
    async def update_status(
        self, run_id: UUID, status: str, error: str | None = None
    ) -> bool:
        """Update run status. Returns True if updated."""
        ...

    @abstractmethod
    async def update_model_name(self, run_id: UUID, model_name: str | None) -> None:
        """Update the model name for a run."""
        ...

    @abstractmethod
    async def update_run_completion(self, run_id: UUID, **kwargs) -> None:
        """Persist completion data (token usage, etc.)."""
        ...

    @abstractmethod
    async def update_run_progress(self, run_id: UUID, **kwargs) -> None:
        """Update run progress fields incrementally."""
        ...

    @abstractmethod
    async def list_inflight(self, before: str | None = None) -> list[dict]:
        """List runs that are still inflight (pending/running)."""
        ...


class NoopRunStore(RunStore):
    """In-memory only store (no persistence)."""

    def __init__(self) -> None:
        self._data: dict[UUID, dict] = {}

    async def put(self, run_id: UUID, **kwargs) -> None:
        if run_id not in self._data:
            self._data[run_id] = {}
        self._data[run_id].update(kwargs)

    async def get(self, run_id: UUID, user_id: UUID | None = None) -> dict | None:
        return self._data.get(run_id)

    async def list_by_thread(
        self, thread_id: UUID, user_id: UUID | None = None, limit: int = 100
    ) -> list[dict]:
        return [
            r for r in self._data.values() if r.get("thread_id") == thread_id
        ][:limit]

    async def update_status(
        self, run_id: UUID, status: str, error: str | None = None
    ) -> bool:
        if run_id in self._data:
            self._data[run_id]["status"] = status
            if error is not None:
                self._data[run_id]["error"] = error
            return True
        return False

    async def update_model_name(self, run_id: UUID, model_name: str | None) -> None:
        if run_id in self._data:
            self._data[run_id]["model_name"] = model_name

    async def update_run_completion(self, run_id: UUID, **kwargs) -> None:
        if run_id in self._data:
            self._data[run_id].update(kwargs)

    async def update_run_progress(self, run_id: UUID, **kwargs) -> None:
        if run_id in self._data:
            self._data[run_id].update(kwargs)

    async def list_inflight(self, before: str | None = None) -> list[dict]:
        inflight = [r for r in self._data.values() if r.get("status") in ("pending", "running")]
        return inflight


class SQLiteRunStore(RunStore):
    """SQLite-backed run store with retry policy."""

    _TABLE_SCHEMA = """
        CREATE TABLE IF NOT EXISTS runs (
            run_id TEXT PRIMARY KEY,
            thread_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            model_name TEXT,
            assistant_id TEXT,
            metadata TEXT DEFAULT '{}',
            kwargs TEXT DEFAULT '{}',
            on_disconnect TEXT DEFAULT 'cancel',
            multitask_strategy TEXT DEFAULT 'reject',
            abort_action TEXT DEFAULT 'interrupt',
            error TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            total_input_tokens INTEGER DEFAULT 0,
            total_output_tokens INTEGER DEFAULT 0,
            total_tokens INTEGER DEFAULT 0,
            llm_call_count INTEGER DEFAULT 0,
            lead_agent_tokens INTEGER DEFAULT 0,
            subagent_tokens INTEGER DEFAULT 0,
            middleware_tokens INTEGER DEFAULT 0,
            message_count INTEGER DEFAULT 0,
            last_ai_message TEXT,
            first_human_message TEXT,
            store_only INTEGER DEFAULT 0
        )
    """

    _INDEXES = [
        "CREATE INDEX IF NOT EXISTS idx_runs_thread_id ON runs(thread_id)",
        "CREATE INDEX IF NOT EXISTS idx_runs_status ON runs(status)",
        "CREATE INDEX IF NOT EXISTS idx_runs_created_at ON runs(created_at)",
    ]

    def __init__(
        self,
        db_path: str = "runs.db",
        retry_policy: PersistenceRetryPolicy | None = None,
    ) -> None:
        self._db_path = db_path
        self._retry_policy = retry_policy or PersistenceRetryPolicy()
        self._lock = asyncio.Lock()
        self._initialized = False

    async def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        async with self._lock:
            if self._initialized:
                return
            import aiosqlite
            async with aiosqlite.connect(self._db_path) as db:
                await db.execute(self._TABLE_SCHEMA)
                for idx in self._INDEXES:
                    await db.execute(idx)
                await db.commit()
            self._initialized = True

    async def _call_with_retry(self, coro):
        """Execute a coroutine with exponential backoff retry."""
        delay = self._retry_policy.initial_delay
        for attempt in range(self._retry_policy.max_attempts):
            try:
                return await coro()
            except Exception as e:
                if attempt == self._retry_policy.max_attempts - 1:
                    raise
                logger.warning("SQLite operation failed (attempt %d): %s", attempt + 1, e)
                await asyncio.sleep(delay)
                delay = min(delay * self._retry_policy.backoff_factor, self._retry_policy.max_delay)
        return None

    async def put(self, run_id: UUID, **kwargs) -> None:
        await self._ensure_initialized()
        import aiosqlite

        async def _put():
            async with aiosqlite.connect(self._db_path) as db:
                kwargs["run_id"] = str(run_id)
                kwargs["updated_at"] = datetime.utcnow().isoformat()
                if "created_at" not in kwargs:
                    kwargs["created_at"] = kwargs["updated_at"]
                for key in ("metadata", "kwargs"):
                    if key in kwargs and isinstance(kwargs[key], dict):
                        import json
                        kwargs[key] = json.dumps(kwargs[key])
                cols = list(kwargs.keys())
                placeholders = [f"${i+1}" for i in range(len(cols))]
                sql = f"INSERT OR REPLACE INTO runs ({', '.join(cols)}) VALUES ({', '.join(placeholders)})"
                await db.execute(sql, tuple(kwargs[c] for c in cols))
                await db.commit()

        await self._call_with_retry(_put())

    async def get(self, run_id: UUID, user_id: UUID | None = None) -> dict | None:
        await self._ensure_initialized()
        import aiosqlite
        import json

        async def _get():
            async with aiosqlite.connect(self._db_path) as db:
                async with db.execute(
                    "SELECT * FROM runs WHERE run_id = ?", (str(run_id),)
                ) as cursor:
                    row = await cursor.fetchone()
                    if not row:
                        return None
                    cols = [desc[0] for desc in cursor.description]
                    result = dict(zip(cols, row))
                    for key in ("metadata", "kwargs"):
                        if key in result and isinstance(result[key], str):
                            result[key] = json.loads(result[key])
                    return result

        return await self._call_with_retry(_get())

    async def list_by_thread(
        self, thread_id: UUID, user_id: UUID | None = None, limit: int = 100
    ) -> list[dict]:
        await self._ensure_initialized()
        import aiosqlite
        import json

        async def _list():
            async with aiosqlite.connect(self._db_path) as db:
                async with db.execute(
                    "SELECT * FROM runs WHERE thread_id = ? ORDER BY created_at DESC LIMIT ?",
                    (str(thread_id), limit),
                ) as cursor:
                    rows = await cursor.fetchall()
                    if not rows:
                        return []
                    cols = [desc[0] for desc in cursor.description]
                    results = []
                    for row in rows:
                        result = dict(zip(cols, row))
                        for key in ("metadata", "kwargs"):
                            if key in result and isinstance(result[key], str):
                                result[key] = json.loads(result[key])
                        results.append(result)
                    return results

        return await self._call_with_retry(_list())

    async def update_status(
        self, run_id: UUID, status: str, error: str | None = None
    ) -> bool:
        await self._ensure_initialized()
        import aiosqlite

        async def _update():
            async with aiosqlite.connect(self._db_path) as db:
                if error is not None:
                    await db.execute(
                        "UPDATE runs SET status = ?, error = ?, updated_at = ? WHERE run_id = ?",
                        (status, error, datetime.utcnow().isoformat(), str(run_id)),
                    )
                else:
                    await db.execute(
                        "UPDATE runs SET status = ?, updated_at = ? WHERE run_id = ?",
                        (status, datetime.utcnow().isoformat(), str(run_id)),
                    )
                await db.commit()
                return db.rowcount > 0

        return await self._call_with_retry(_update())

    async def update_model_name(self, run_id: UUID, model_name: str | None) -> None:
        await self._ensure_initialized()
        import aiosqlite

        async def _update():
            async with aiosqlite.connect(self._db_path) as db:
                await db.execute(
                    "UPDATE runs SET model_name = ?, updated_at = ? WHERE run_id = ?",
                    (model_name, datetime.utcnow().isoformat(), str(run_id)),
                )
                await db.commit()

        await self._call_with_retry(_update())

    async def update_run_completion(self, run_id: UUID, **kwargs) -> None:
        await self._ensure_initialized()
        import aiosqlite
        import json

        async def _update():
            async with aiosqlite.connect(self._db_path) as db:
                if "metadata" in kwargs:
                    kwargs["metadata"] = json.dumps(kwargs["metadata"])
                kwargs["updated_at"] = datetime.utcnow().isoformat()
                set_clause = ", ".join(f"{k} = ?" for k in kwargs.keys())
                await db.execute(
                    f"UPDATE runs SET {set_clause} WHERE run_id = ?",
                    (*kwargs.values(), str(run_id)),
                )
                await db.commit()

        await self._call_with_retry(_update())

    async def update_run_progress(self, run_id: UUID, **kwargs) -> None:
        await self._ensure_initialized()
        await self.update_run_completion(run_id, **kwargs)

    async def list_inflight(self, before: str | None = None) -> list[dict]:
        await self._ensure_initialized()
        import aiosqlite
        import json

        async def _list():
            async with aiosqlite.connect(self._db_path) as db:
                if before:
                    async with db.execute(
                        "SELECT * FROM runs WHERE status IN ('pending', 'running') AND created_at < ?",
                        (before,),
                    ) as cursor:
                        rows = await cursor.fetchall()
                else:
                    async with db.execute(
                        "SELECT * FROM runs WHERE status IN ('pending', 'running')"
                    ) as cursor:
                        rows = await cursor.fetchall()

                if not rows:
                    return []
                cols = [desc[0] for desc in cursor.description]
                results = []
                for row in rows:
                    result = dict(zip(cols, row))
                    for key in ("metadata", "kwargs"):
                        if key in result and isinstance(result[key], str):
                            result[key] = json.loads(result[key])
                    results.append(result)
                return results

        return await self._call_with_retry(_list())
