"""Integration test fixtures."""
from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient

from app.db.dbengine.core import DatabaseEngine
from app.settings import get_settings
from app.web.application import get_app

# Get alembic config path
ALEMBIC_INI = Path(__file__).parent.parent.parent / "app" / "db" / "migrations" / "alembic.ini"


@pytest.fixture(scope="session")
def alembic_cfg() -> Config:
    """Create Alembic configuration."""
    cfg = Config(str(ALEMBIC_INI))
    return cfg


@pytest.fixture(scope="session")
def test_db_url() -> str:
    """Generate unique test database URL."""
    db_name = f"test_{uuid4()[:8]}.db"
    return f"sqlite+aiosqlite:///{db_name}"


@pytest.fixture(scope="session")
def setup_test_db(alembic_cfg: Config, test_db_url: str) -> str:
    """Run Alembic migrations for test database.

    Creates the test database with proper schema, yields the URL,
    and cleans up the file after test session.
    """
    # Set test database URL
    alembic_cfg.config.set_main_option("sqlalchemy.url", test_db_url)

    # Run migrations
    command.upgrade(alembic_cfg, "head")

    yield test_db_url

    # Cleanup: delete test database file
    db_path = Path(test_db_url.replace("sqlite+aiosqlite:///", ""))
    if db_path.exists():
        db_path.unlink()


@pytest.fixture
async def db_engine(test_db_url: str) -> AsyncGenerator[DatabaseEngine, None]:
    """Create database engine for a test.

    Note: Schema is already created by setup_test_db (session scope).
    This fixture provides engine-level access for service layer tests.
    """
    engine = DatabaseEngine(url=test_db_url)
    try:
        yield engine
    finally:
        await engine.close()


@pytest.fixture
async def api_client(setup_test_db: str) -> AsyncGenerator[AsyncClient, None]:
    """Base AsyncClient - unauthenticated.

    This is the raw client. For tests, prefer authed_api_client or noauthed_api_client.
    """
    app = get_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac