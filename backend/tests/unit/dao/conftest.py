"""DAO unit test fixtures."""
from __future__ import annotations

import os
from collections.abc import AsyncIterator
from pathlib import Path

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.db.models import Base
from app.db.session import make_engine

# Force test DB path before any app import.
_BACKEND_ROOT = Path(__file__).resolve().parents[3]
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_BACKEND_ROOT / 'test.db'}"


@pytest_asyncio.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    """Per-test AsyncEngine: drop_all + create_all before each test."""
    eng: AsyncEngine = make_engine(os.environ["DATABASE_URL"])
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    async with AsyncSession(engine, expire_on_commit=False) as s:
        yield s
