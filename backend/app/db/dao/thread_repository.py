"""Thread ORM repository (soft-delete aware)."""

from __future__ import annotations

from typing import cast
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.exception.exception import ResourceNotFoundError
from app.db.models import Thread


class ThreadRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, thread: Thread) -> Thread:
        self.session.add(thread)
        await self.session.flush()
        await self.session.refresh(thread)
        return thread

    async def find_by_id(self, thread_id: UUID) -> Thread | None:
        return cast(
            Thread | None,
            await self.session.scalar(
                select(Thread).where(Thread.id == thread_id, Thread.not_deleted())
            ),
        )

    async def find_by_id_and_user(self, thread_id: UUID, user_id: UUID) -> Thread | None:
        return cast(
            Thread | None,
            await self.session.scalar(
                select(Thread).where(
                    Thread.id == thread_id,
                    Thread.user_id == user_id,
                    Thread.not_deleted(),
                )
            ),
        )

    async def find_by_id_and_user_or_fail(self, thread_id: UUID, user_id: UUID) -> Thread:
        thread = await self.find_by_id_and_user(thread_id, user_id)
        if thread is None:
            raise ResourceNotFoundError(f"Thread {thread_id} not found for user {user_id}")
        return thread

    async def list_by_user_id(
        self, user_id: UUID, *, limit: int = 50, offset: int = 0
    ) -> list[Thread]:
        stmt = (
            select(Thread)
            .where(Thread.user_id == user_id, Thread.not_deleted())
            .order_by(func.coalesce(Thread.updated_at, Thread.created_at).desc(), Thread.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return list((await self.session.execute(stmt)).scalars())

    async def update_title(self, thread_id: UUID, user_id: UUID, title: str) -> Thread | None:
        result = await self.session.execute(
            update(Thread)
            .where(Thread.id == thread_id, Thread.user_id == user_id, Thread.not_deleted())
            .values(title=title, updated_at=func.now())
            .returning(Thread)
            .execution_options(synchronize_session="fetch")
        )
        return result.scalar_one_or_none()

    async def soft_delete(self, thread_id: UUID, user_id: UUID) -> bool:
        result = await self.session.execute(
            update(Thread)
            .where(
                Thread.id == thread_id,
                Thread.user_id == user_id,
                Thread.deleted_at.is_(None),
            )
            .values(deleted_at=func.now())
        )
        return (result.rowcount or 0) > 0  # type: ignore[attr-defined]
