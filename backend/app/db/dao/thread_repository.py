"""Thread repository with domain-specific operations."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import text

from app.common.exception import ResourceNotFoundError
from app.db.dao.generic_repository import GenericRepository
from app.db.dbengine.core import DatabaseEngine
from app.db.models.thread import Thread


class ThreadRepository(GenericRepository):
    """Repository for thread operations."""

    def __init__(self, engine: DatabaseEngine) -> None:
        super().__init__(engine=engine)

    async def create(self, thread: Thread) -> Thread:
        return await self.insert(thread)

    async def find_by_id_and_user(self, thread_id: UUID, user_id: UUID) -> Thread | None:
        """Find thread by ID with user_id filter (resource-level auth)."""
        stmt = text("""
            SELECT * FROM threads
            WHERE id = :id AND user_id = :user_id
            AND (deleted_at IS NULL OR deleted_at > CURRENT_TIMESTAMP)
        """).bindparams(id=thread_id, user_id=user_id)
        row = await self.engine.at_most_one(stmt)
        return Thread.from_row(row) if row else None

    async def find_by_id_and_user_or_fail(self, thread_id: UUID, user_id: UUID) -> Thread:
        result = await self.find_by_id_and_user(thread_id, user_id)
        if not result:
            raise ResourceNotFoundError(f"Thread {thread_id} not found for user {user_id}")
        return result

    async def list_by_user_id(
        self, user_id: UUID, *, limit: int = 50, offset: int = 0
    ) -> list[Thread]:
        """List threads for a user, ordered by most recent."""
        stmt = text("""
            SELECT * FROM threads
            WHERE user_id = :user_id
            AND (deleted_at IS NULL OR deleted_at > CURRENT_TIMESTAMP)
            ORDER BY updated_at DESC
            LIMIT :limit OFFSET :offset
        """).bindparams(user_id=user_id, limit=limit, offset=offset)
        rows = await self.engine.all(stmt)
        return [Thread.from_row(row) for row in rows]

    async def update_title(self, thread_id: UUID, user_id: UUID, title: str) -> Thread | None:
        """Update thread title with user_id filter."""
        stmt = text("""
            UPDATE threads
            SET title = :title
            WHERE id = :id AND user_id = :user_id
            AND (deleted_at IS NULL OR deleted_at > CURRENT_TIMESTAMP)
            RETURNING *
        """).bindparams(id=thread_id, user_id=user_id, title=title)
        row = await self.engine.at_most_one(stmt)
        return Thread.from_row(row) if row else None

    async def soft_delete(self, thread_id: UUID, user_id: UUID) -> bool:
        """Soft delete a thread."""

        stmt = text("""
            UPDATE threads
            SET deleted_at = :deleted_at
            WHERE id = :id AND user_id = :user_id
            AND deleted_at IS NULL
        """).bindparams(
            id=thread_id,
            user_id=user_id,
            deleted_at=datetime.now(UTC),
        )
        result = await self.engine.execute(stmt)
        return result.rowcount > 0  # type: ignore[no-any-return,attr-defined]
