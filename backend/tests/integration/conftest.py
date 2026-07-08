"""Integration test fixtures."""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncGenerator, Generator
from contextlib import AsyncExitStack
from pathlib import Path
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.app_context.app_context import AppContext, create_checkpointer
from app.common.runs.manager import RunManager
from app.common.stream_bridge.memory import MemoryStreamBridge
from app.core.backtest.registry import BacktestRegistry
from app.core.chat.memory.wiring import install_memory_subsystem, shutdown_memory_subsystem
from app.db.models import Base
from app.db.session import make_engine, make_session_factory
from app.settings import get_settings, reload_settings
from app.web.application import get_app
from tests.integration.client import APITestClient


@pytest.fixture(scope="session")
def test_db_url(tmp_path_factory: pytest.TempPathFactory) -> str:
    """Generate unique test database URL with absolute path."""
    db_name = f"test_{str(uuid4())[:8]}.db"
    tmp_dir = tmp_path_factory.mktemp("test_db")
    db_path = tmp_dir / db_name
    return f"sqlite+aiosqlite:///{db_path}"


@pytest.fixture(scope="session")
def setup_test_db(test_db_url: str) -> Generator[str]:
    """Set up test database schema via Base.metadata.create_all().

    Replaces the previous alembic-based setup. Sets DATABASE_URL env var so
    Settings picks it up, runs create_all, then restores the env.
    """
    original_db_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = test_db_url
    reload_settings()

    try:
        engine = make_engine(test_db_url)

        async def _create() -> None:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

        asyncio.run(_create())
        yield test_db_url
    finally:
        if original_db_url is not None:
            os.environ["DATABASE_URL"] = original_db_url
        else:
            os.environ.pop("DATABASE_URL", None)
        reload_settings()


@pytest.fixture
async def test_app_context(
    setup_test_db: str,
    tmp_path: Path,
) -> AsyncGenerator[AppContext]:
    """Create test app context with test database and sqlite checkpointer.

    Function-scoped on purpose: the checkpointer's ``asyncio.Lock`` is bound
    to the event loop in which it was constructed, and pytest-asyncio's
    auto-mode spins up a fresh loop per test. A session-scoped fixture would
    leak the lock across loops and trigger
    ``RuntimeError: <Lock> is bound to a different event loop`` from
    LangGraph's SQLite checkpointer.

    Uses the new per-request pattern: services are NOT pre-constructed;
    they are built per-request via the lifespan_service dependencies
    in app/web/lifespan_service.py.
    """
    engine = make_engine(setup_test_db)
    session_factory = make_session_factory(engine)

    lifespan_exit_stack = AsyncExitStack()
    checkpoint_db = Path(tmp_path) / "checkpoints.db"
    checkpointer = await create_checkpointer(
        lifespan_exit_stack,
        backend="sqlite",
        connection_string=str(checkpoint_db),
    )

    # Wire memory evolution subsystem (P4): debounced update queue + hook.
    cfg = get_settings()
    memory_queue = install_memory_subsystem(cfg, session_factory)

    run_manager = RunManager()
    stream_bridge = MemoryStreamBridge(queue_maxsize=100)
    backtest_registry = BacktestRegistry()

    app_context = AppContext(
        session_factory=session_factory,
        checkpointer=checkpointer,
        stream_bridge=stream_bridge,
        run_manager=run_manager,
        backtest_registry=backtest_registry,
        lifespan_exit_stack=lifespan_exit_stack,
    )

    yield app_context

    shutdown_memory_subsystem(memory_queue)
    await app_context.close()


@pytest.fixture
async def api_client(test_app_context: AppContext) -> AsyncGenerator[AsyncClient]:
    """Base AsyncClient - unauthenticated."""
    app = get_app()
    app.state.app_context = test_app_context
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def authed_api_client(api_client: AsyncClient) -> APITestClient:
    """Auto-login and return APITestClient with cookies set."""
    client = APITestClient(api_client)
    await client.post(
        "/api/v1/auth/register",
        json={
            "email": f"{uuid4()}@test.com",
            "password": "TestPassword123!",
            "full_name": "Test User",
        },
    )
    return client


@pytest.fixture
async def noauthed_api_client(api_client: AsyncClient) -> APITestClient:
    """APITestClient without authentication."""
    return APITestClient(api_client)
