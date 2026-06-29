"""Async SQLAlchemy session factory."""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def make_engine(url: str, *, echo: bool = False) -> AsyncEngine:
    """Create AsyncEngine for the given database URL."""
    return create_async_engine(url=url, echo=echo)


def make_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Build an async_sessionmaker bound to the engine.

    expire_on_commit=False so ORM attributes remain accessible after commit
    (matches the pattern `instance = await session.get(...)` followed by use
    outside the session).
    """
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_session(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: yield an AsyncSession and ensure cleanup."""
    async with session_factory() as session:
        yield session
