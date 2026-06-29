"""Memory service - business logic for user memory management."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.exception.exception import ResourceNotFoundError
from app.db.dao.memory_repository import MemoryRepository
from app.db.models.memory import MemoryFact, UserMemory


@dataclass
class UserMemoryContext:
    """User memory context for injection into prompts."""

    memories: list[UserMemory]
    facts: list[MemoryFact]

    def to_prompt_string(self) -> str:
        sections: list[str] = []
        if self.memories:
            sections.append("[User Memories]")
            for mem in self.memories:
                confidence_str = f" (confidence: {mem.confidence:.0%})" if mem.confidence < 1.0 else ""
                source_str = f" [source: {mem.source}]" if mem.source else ""
                sections.append(f"- {mem.content}{confidence_str}{source_str}")
        if self.facts:
            sections.append("[User Facts]")
            for fact in self.facts:
                sections.append(f"- {fact.content}")
        if not sections:
            return ""
        return "\n".join(sections)


class MemoryService:
    """Service for memory operations.

    Receives a per-request AsyncSession. Flushes but never commits.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_user_memory(self, user_id: UUID) -> UserMemoryContext:
        """Get aggregated memory context for a user."""
        repo = MemoryRepository(self._session)
        memories = await repo.find_memories_by_user(user_id)
        facts = await repo.find_facts_by_user(user_id)
        return UserMemoryContext(memories=memories, facts=facts)

    async def add_memory(
        self,
        user_id: UUID,
        memory_type: str,
        content: str,
        *,
        confidence: float = 1.0,
        source: str | None = None,
    ) -> UserMemory:
        """Add a new user memory."""
        memory = UserMemory(
            id=uuid4(),
            user_id=user_id,
            memory_type=memory_type,
            content=content,
            confidence=confidence,
            source=source,
            created_at=datetime.now(UTC),
        )
        return await MemoryRepository(self._session).create_memory(memory)

    async def add_fact(
        self,
        user_id: UUID,
        fact_type: str,
        content: str,
        *,
        embedding: list[float] | None = None,
    ) -> MemoryFact:
        """Add a new memory fact."""
        fact = MemoryFact(
            id=uuid4(),
            user_id=user_id,
            fact_type=fact_type,
            content=content,
            embedding=embedding,
            created_at=datetime.now(UTC),
        )
        return await MemoryRepository(self._session).create_fact(fact)

    async def delete_memory(self, memory_id: UUID, user_id: UUID) -> None:
        """Delete a user memory; raise ResourceNotFoundError if not found."""
        deleted = await MemoryRepository(self._session).delete_memory(memory_id, user_id)
        if not deleted:
            raise ResourceNotFoundError(f"Memory {memory_id} not found")

    async def delete_fact(self, fact_id: UUID, user_id: UUID) -> None:
        """Delete a memory fact; raise ResourceNotFoundError if not found."""
        deleted = await MemoryRepository(self._session).delete_fact(fact_id, user_id)
        if not deleted:
            raise ResourceNotFoundError(f"Fact {fact_id} not found")
