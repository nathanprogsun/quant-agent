"""Memory repository with domain-specific operations."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import text

from app.db.dao.generic_repository import GenericRepository
from app.db.dbengine.core import DatabaseEngine
from app.db.models.memory import MemoryFact, UserMemory


class MemoryRepository(GenericRepository):
    """Repository for memory operations."""

    def __init__(self, engine: DatabaseEngine) -> None:
        super().__init__(engine=engine)

    # ── UserMemory operations ─────────────────────────────────

    async def create_memory(self, memory: UserMemory) -> UserMemory:
        """Create a new user memory."""
        return await self.insert(memory)

    async def find_memories_by_user(
        self,
        user_id: UUID,
        *,
        memory_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[UserMemory]:
        """Find memories by user_id with optional type filter."""
        if memory_type:
            stmt = text("""
                SELECT * FROM user_memories
                WHERE user_id = :user_id AND memory_type = :memory_type
                ORDER BY created_at DESC
                LIMIT :limit OFFSET :offset
            """).bindparams(user_id=user_id, memory_type=memory_type, limit=limit, offset=offset)
        else:
            stmt = text("""
                SELECT * FROM user_memories
                WHERE user_id = :user_id
                ORDER BY created_at DESC
                LIMIT :limit OFFSET :offset
            """).bindparams(user_id=user_id, limit=limit, offset=offset)
        rows = await self.engine.all(stmt)
        return [UserMemory.from_row(row) for row in rows]

    async def delete_memory(self, memory_id: UUID, user_id: UUID) -> bool:
        """Delete a memory by ID with user_id filter."""
        stmt = text("""
            DELETE FROM user_memories
            WHERE id = :id AND user_id = :user_id
        """).bindparams(id=memory_id, user_id=user_id)
        result = await self.engine.execute(stmt)
        return result.rowcount > 0  # type: ignore[no-any-return, attr-defined]

    # ── MemoryFact operations ──────────────────────────────────

    async def create_fact(self, fact: MemoryFact) -> MemoryFact:
        """Create a new memory fact."""
        return await self.insert(fact)

    async def find_facts_by_user(
        self,
        user_id: UUID,
        *,
        fact_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[MemoryFact]:
        """Find facts by user_id with optional type filter."""
        if fact_type:
            stmt = text("""
                SELECT * FROM memory_facts
                WHERE user_id = :user_id AND fact_type = :fact_type
                ORDER BY created_at DESC
                LIMIT :limit OFFSET :offset
            """).bindparams(user_id=user_id, fact_type=fact_type, limit=limit, offset=offset)
        else:
            stmt = text("""
                SELECT * FROM memory_facts
                WHERE user_id = :user_id
                ORDER BY created_at DESC
                LIMIT :limit OFFSET :offset
            """).bindparams(user_id=user_id, limit=limit, offset=offset)
        rows = await self.engine.all(stmt)
        return [MemoryFact.from_row(row) for row in rows]

    async def find_fact_by_id(self, fact_id: UUID, user_id: UUID) -> MemoryFact | None:
        """Find a fact by ID with user_id filter."""
        stmt = text("""
            SELECT * FROM memory_facts
            WHERE id = :id AND user_id = :user_id
        """).bindparams(id=fact_id, user_id=user_id)
        row = await self.engine.at_most_one(stmt)
        return MemoryFact.from_row(row) if row else None

    async def delete_fact(self, fact_id: UUID, user_id: UUID) -> bool:
        """Delete a fact by ID with user_id filter."""
        stmt = text("""
            DELETE FROM memory_facts
            WHERE id = :id AND user_id = :user_id
        """).bindparams(id=fact_id, user_id=user_id)
        result = await self.engine.execute(stmt)
        return result.rowcount > 0  # type: ignore[no-any-return, attr-defined]
