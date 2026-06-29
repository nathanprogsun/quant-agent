"""Memory ORM repository (UserMemory + MemoryFact)."""
from __future__ import annotations

from typing import cast
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import MemoryFact, UserMemory


class MemoryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ---- UserMemory ----

    async def create_memory(self, memory: UserMemory) -> UserMemory:
        self.session.add(memory)
        await self.session.flush()
        await self.session.refresh(memory)
        return memory

    async def find_memories_by_user(
        self,
        user_id: UUID,
        *,
        memory_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[UserMemory]:
        stmt = (
            select(UserMemory)
            .where(UserMemory.user_id == user_id)
            .order_by(UserMemory.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        if memory_type is not None:
            stmt = stmt.where(UserMemory.memory_type == memory_type)
        return list((await self.session.execute(stmt)).scalars())

    async def delete_memory(self, memory_id: UUID, user_id: UUID) -> bool:
        result = await self.session.execute(
            delete(UserMemory).where(
                UserMemory.id == memory_id, UserMemory.user_id == user_id
            )
        )
        return (result.rowcount or 0) > 0

    # ---- MemoryFact ----

    async def create_fact(self, fact: MemoryFact) -> MemoryFact:
        self.session.add(fact)
        await self.session.flush()
        await self.session.refresh(fact)
        return fact

    async def find_facts_by_user(
        self,
        user_id: UUID,
        *,
        fact_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[MemoryFact]:
        stmt = (
            select(MemoryFact)
            .where(MemoryFact.user_id == user_id)
            .order_by(MemoryFact.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        if fact_type is not None:
            stmt = stmt.where(MemoryFact.fact_type == fact_type)
        return list((await self.session.execute(stmt)).scalars())

    async def find_fact_by_id(self, fact_id: UUID, user_id: UUID) -> MemoryFact | None:
        return cast(
            MemoryFact | None,
            await self.session.scalar(
                select(MemoryFact).where(
                    MemoryFact.id == fact_id, MemoryFact.user_id == user_id
                )
            ),
        )

    async def delete_fact(self, fact_id: UUID, user_id: UUID) -> bool:
        result = await self.session.execute(
            delete(MemoryFact).where(
                MemoryFact.id == fact_id, MemoryFact.user_id == user_id
            )
        )
        return (result.rowcount or 0) > 0
