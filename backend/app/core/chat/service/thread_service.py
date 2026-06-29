"""Thread service — business logic for chat thread management."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.exception import ResourceNotFoundError
from app.common.runs.manager import RunManager, RunRecord
from app.db.dao.thread_repository import ThreadRepository
from app.db.models.thread import Thread


class ThreadService:
    """Service for thread CRUD operations.

    Receives a per-request AsyncSession. Flushes but never commits.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        thread_id: UUID,
        user_id: UUID,
        *,
        title: str | None = None,
        model_name: str | None = None,
    ) -> Thread:
        """Create a thread if it doesn't exist, otherwise return existing."""
        repo = ThreadRepository(self._session)
        existing = await repo.find_by_id_and_user(thread_id, user_id)
        if existing:
            return existing

        thread = Thread(
            id=thread_id,
            user_id=user_id,
            title=title,
            model_name=model_name,
            created_at=datetime.now(UTC),
        )
        return await repo.create(thread)

    async def get(self, thread_id: UUID, user_id: UUID) -> Thread:
        """Get thread by ID with user_id authorization."""
        return await ThreadRepository(self._session).find_by_id_and_user_or_fail(
            thread_id, user_id
        )

    async def assert_stream_access(self, thread_id: UUID, user_id: UUID) -> None:
        """Allow auto-create for new threads; deny cross-user access."""
        thread = await ThreadRepository(self._session).find_by_id(thread_id)
        if thread is not None and thread.user_id != user_id:
            raise ResourceNotFoundError(f"Thread {thread_id} not found for user {user_id}")

    async def list_by_user_id(
        self, user_id: UUID, *, limit: int = 50, offset: int = 0
    ) -> list[Thread]:
        """List threads for a user."""
        return await ThreadRepository(self._session).list_by_user_id(
            user_id, limit=limit, offset=offset
        )

    async def update_title_or_raise(
        self, thread_id: UUID, user_id: UUID, title: str
    ) -> Thread:
        """Update thread title; raise ResourceNotFoundError if not found."""
        thread = await ThreadRepository(self._session).update_title(
            thread_id, user_id, title
        )
        if thread is None:
            raise ResourceNotFoundError(f"Thread {thread_id} not found")
        return thread

    async def delete_or_raise(self, thread_id: UUID, user_id: UUID) -> None:
        """Soft delete a thread; raise ResourceNotFoundError if not found."""
        deleted = await ThreadRepository(self._session).soft_delete(thread_id, user_id)
        if not deleted:
            raise ResourceNotFoundError(f"Thread {thread_id} not found")


class RunService:
    """Service for run-related operations.

    Wraps a RunManager and enforces ownership/thread scoping so that
    HTTP views can stay thin.
    """

    def __init__(self, run_manager: RunManager) -> None:
        self._run_manager = run_manager

    @property
    def manager(self) -> RunManager:
        """Underlying RunManager (for callers that need direct access, e.g. SSE)."""
        return self._run_manager

    async def list_for_user(self, thread_id: UUID, user_id: UUID) -> list[RunRecord]:
        """List runs in thread, filtered by user ownership."""
        records = await self._run_manager.list_by_thread(thread_id)
        return [r for r in records if r.user_id == user_id]

    async def get_for_user(self, run_id: UUID, thread_id: UUID, user_id: UUID) -> RunRecord:
        """Get run with ownership check.

        Raises:
            ResourceNotFoundError: if not found, not in this thread, or not
                owned by the user.
        """
        record = await self._run_manager.get(run_id)
        if record is None or record.thread_id != thread_id or record.user_id != user_id:
            raise ResourceNotFoundError(f"Run {run_id} not found")
        return record

    async def cancel_for_user(self, run_id: UUID, thread_id: UUID, user_id: UUID) -> None:
        """Cancel run with ownership check.

        Raises:
            ResourceNotFoundError: if not found, not in this thread, not
                owned by the user, or already finished.
        """
        await self.get_for_user(run_id, thread_id, user_id)
        cancelled = await self._run_manager.cancel(run_id)
        if not cancelled:
            raise ResourceNotFoundError(
                f"Run {run_id} not found or already finished"
            )
