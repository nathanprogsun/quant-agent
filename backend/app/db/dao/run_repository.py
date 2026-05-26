"""Run repository with domain-specific operations."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import text

from app.db.dao.generic_repository import GenericRepository
from app.db.models.run import Run

if TYPE_CHECKING:
    from app.db.dbengine.core import DatabaseEngine


class RunRepository(GenericRepository):
    """Repository for run operations."""

    def __init__(self, engine: DatabaseEngine) -> None:
        super().__init__(engine=engine)

    async def create(self, run: Run) -> Run:
        return await self.insert(run)

    async def find_by_id(self, run_id: UUID) -> Run | None:
        stmt = text("""
            SELECT * FROM runs WHERE id = :id
        """).bindparams(id=run_id)
        row = await self.engine.at_most_one(stmt)
        return Run.from_row(row) if row else None

    async def list_by_thread(
        self, thread_id: UUID, *, limit: int = 50, offset: int = 0
    ) -> list[Run]:
        """List runs for a thread, ordered by most recent."""
        stmt = text("""
            SELECT * FROM runs
            WHERE thread_id = :thread_id
            ORDER BY created_at DESC
            LIMIT :limit OFFSET :offset
        """).bindparams(thread_id=thread_id, limit=limit, offset=offset)
        rows = await self.engine.all(stmt)
        return [Run.from_row(row) for row in rows]
