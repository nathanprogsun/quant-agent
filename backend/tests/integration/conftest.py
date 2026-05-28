"""Integration test fixtures."""
from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient

from app.app_context.app_context import AppContext, LifeSpanService
from app.common.runs.manager import RunManager
from app.common.stream_bridge.memory import MemoryStreamBridge
from app.core.auth.service.auth_service import get_auth_service_by_engine
from app.core.chat.service.thread_service import get_thread_service_by_engine
from app.core.user.service.user_service import get_user_service_by_engine
from app.db.dbengine.core import DatabaseEngine
from app.settings import reload_settings
from app.web.application import get_app
from tests.integration.client import APITestClient

# Get alembic config path (alembic.ini is at project root: backend/alembic.ini)
# Path(__file__) = tests/integration/conftest.py
# parent.parent.parent = backend/ (project root)
ALEMBIC_INI = Path(__file__).parent.parent.parent / "alembic.ini"


@pytest.fixture(scope="session")
def test_db_url(tmp_path_factory: pytest.TempPathFactory) -> str:
    """Generate unique test database URL with absolute path."""
    db_name = f"test_{str(uuid4())[:8]}.db"
    tmp_dir = tmp_path_factory.mktemp("test_db")
    db_path = tmp_dir / db_name
    return f"sqlite+aiosqlite:///{db_path}"


@pytest.fixture(scope="session")
def alembic_cfg() -> Config:
    """Create Alembic configuration."""
    return Config(file_=str(ALEMBIC_INI), ini_section="alembic")


@pytest.fixture(scope="session")
def setup_test_db(alembic_cfg: Config, test_db_url: str) -> str:
    """Run Alembic migrations for test database.

    Sets DATABASE_URL env var so migrations use the test database,
    runs migrations, and cleans up after test session.
    """
    # Override DATABASE_URL so env.py uses our test database
    original_db_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = test_db_url

    # Reload settings to pick up the new DATABASE_URL
    reload_settings()

    try:
        # Run migrations
        command.upgrade(alembic_cfg, "head")
        yield test_db_url
    finally:
        # Restore original DATABASE_URL
        if original_db_url is not None:
            os.environ["DATABASE_URL"] = original_db_url
        else:
            os.environ.pop("DATABASE_URL", None)
        # Reload settings again to restore original
        reload_settings()


@pytest.fixture(scope="session")
async def test_app_context(setup_test_db: str) -> AppContext:
    """Create test app context with test database."""
    engine = DatabaseEngine(url=setup_test_db)

    # Create services with test engine using factory functions
    auth_service = get_auth_service_by_engine(db_engine=engine)
    user_service = get_user_service_by_engine(db_engine=engine)
    thread_service = get_thread_service_by_engine(db_engine=engine)

    # Create RunManager for run lifecycle management
    run_manager = RunManager()

    # Create StreamBridge for SSE
    stream_bridge = MemoryStreamBridge(queue_maxsize=100)

    # Create HTTP client for external calls
    http_aclient = AsyncClient()

    lifespan_service = LifeSpanService(
        auth_service=auth_service,
        user_service=user_service,
        thread_service=thread_service,
    )

    app_context = AppContext(
        main_db=engine,
        http_aclient=http_aclient,
        lifespan_service=lifespan_service,
        run_manager=run_manager,
        stream_bridge=stream_bridge,
    )

    yield app_context

    # Cleanup
    await http_aclient.aclose()
    await stream_bridge.close()
    await engine.close()


@pytest.fixture
async def api_client(test_app_context: AppContext) -> AsyncGenerator[AsyncClient, None]:
    """Base AsyncClient - unauthenticated.

    Sets up app context before yielding.
    """
    app = get_app()
    app.state.app_context = test_app_context
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def authed_api_client(api_client: AsyncClient) -> APITestClient:
    """Auto-login and return APITestClient with cookies set.

    Registers a new user and returns client ready for authenticated requests.
    Each call creates a new user with unique email.
    """
    client = APITestClient(api_client)
    await client.post("/api/v1/auth/register", json={
        "email": f"{uuid4()}@test.com",
        "password": "TestPassword123!",
        "full_name": "Test User",
    })
    return client


@pytest.fixture
async def noauthed_api_client(api_client: AsyncClient) -> APITestClient:
    """APITestClient without authentication.

    Use this to test unauthenticated access (expects 401).
    """
    return APITestClient(api_client)
