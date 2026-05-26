"""Thread service — business logic for chat thread management."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from app.db.dao.thread_repository import ThreadRepository
from app.db.dbengine.core import DatabaseEngine
from app.db.models.thread import Thread


class ThreadService:
    """Service for thread CRUD operations."""

    def __init__(self, thread_repository: ThreadRepository) -> None:
        self._repo = thread_repository

    async def create_or_update(
        self,
        thread_id: UUID,
        user_id: UUID,
        *,
        model_name: str | None = None,
    ) -> Thread:
        """Create a thread if it doesn't exist, otherwise return existing."""
        existing = await self._repo.find_by_id_and_user(thread_id, user_id)
        if existing:
            return existing

        thread = Thread(
            id=thread_id,
            user_id=user_id,
            model_name=model_name,
            created_at=datetime.now(UTC),
        )
        return await self._repo.create(thread)

    async def get(self, thread_id: UUID, user_id: UUID) -> Thread:
        """Get thread by ID with user_id authorization."""
        return await self._repo.find_by_id_and_user_or_fail(thread_id, user_id)

    async def list_by_user_id(
        self, user_id: UUID, *, limit: int = 50, offset: int = 0
    ) -> list[Thread]:
        """List threads for a user."""
        return await self._repo.list_by_user_id(user_id, limit=limit, offset=offset)

    async def update_title(self, thread_id: UUID, user_id: UUID, title: str) -> Thread | None:
        """Update thread title."""
        return await self._repo.update_title(thread_id, user_id, title)

    async def delete(self, thread_id: UUID, user_id: UUID) -> bool:
        """Soft delete a thread."""
        return await self._repo.soft_delete(thread_id, user_id)


def get_thread_service_by_engine(db_engine: DatabaseEngine) -> ThreadService:
    """Factory function to create ThreadService with dependencies."""
    thread_repository = ThreadRepository(engine=db_engine)
    return ThreadService(thread_repository=thread_repository)
