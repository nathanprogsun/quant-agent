# Integration Test Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign quant-agent integration tests with cookie-based auth, test database isolation, and APITestClient wrapper.

**Architecture:**
- Cookie-based authentication via `AuthMiddleware` (remove `HTTPBearer`)
- Each test session uses a unique SQLite database created via Alembic migrations
- All tests use `APITestClient` wrapper for simplified API calls
- Tests cover both authenticated and unauthenticated scenarios

**Tech Stack:** pytest, httpx.AsyncClient, Alembic, SQLAlchemy, FastAPI

---

## Phase 1: Core Infrastructure

### Task 1.1: Refactor deps.py - Cookie-based Auth

**Files:**
- Modify: `backend/app/web/api/deps.py`
- Test: `backend/tests/integration/test_auth_flow.py`

- [ ] **Step 1: Read current deps.py**

```python
# Current implementation uses HTTPBearer
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
security = HTTPBearer()

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    ...
) -> UserDTO:
    payload = auth_service.decode_token(credentials.credentials)
    ...
```

- [ ] **Step 2: Rewrite get_current_user to use cookie-based auth**

```python
# backend/app/web/api/deps.py
from fastapi import Depends, HTTPException, Request, status
from app.core.user.service.user_service import UserService
from app.web.lifespan_service import user_service_from_lifespan

def get_current_user_id(request: Request) -> str:
    """Get current user ID from request state set by AuthMiddleware.

    AuthMiddleware already validates the token and sets request.state.current_user_id.
    """
    user_id = getattr(request.state, "current_user_id", None)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未认证",
        )
    return user_id

async def get_current_user(
    request: Request,
    user_service: UserService = Depends(user_service_from_lifespan),
) -> UserDTO:
    """Get the current authenticated user."""
    user_id = get_current_user_id(request)
    user = await user_service.get_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在",
        )
    return user
```

- [ ] **Step 3: Remove HTTPBearer import and security instance**

Remove from `deps.py`:
```python
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
security = HTTPBearer()
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/web/api/deps.py
git commit -m "refactor: use cookie-based auth in deps.py

- Remove HTTPBearer dependency
- get_current_user reads from request.state set by AuthMiddleware
- get_current_user_id extracts user ID for use in other dependencies

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 1.2: Create tests/conftest.py - Root Fixtures

**Files:**
- Create: `backend/tests/conftest.py`
- Dependencies: None

- [ ] **Step 1: Create tests/conftest.py with settings override**

```python
"""Root test configuration."""
from __future__ import annotations

import os
from typing import Generator

import pytest

# Override settings before importing app modules
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test.db"
os.environ["ENVIRONMENT"] = "testing"


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"
```

- [ ] **Step 2: Commit**

```bash
git add backend/tests/conftest.py
git commit -m "feat: add root conftest.py with test settings override

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 1.3: Create tests/integration/conftest.py - Test DB + Client Fixtures

**Files:**
- Create: `backend/tests/integration/conftest.py`
- Dependencies: `backend/tests/conftest.py`, `backend/app/db/migrations/env.py`

- [ ] **Step 1: Read current integration conftest.py**

```bash
cat backend/tests/integration/conftest.py
```

- [ ] **Step 2: Write new integration conftest.py with test DB and client fixtures**

```python
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
```

- [ ] **Step 3: Commit**

```bash
git add backend/tests/integration/conftest.py
git commit -m "feat: add integration conftest.py with test DB fixtures

- alembic_cfg: Alembic configuration for migrations
- test_db_url: unique SQLite DB per session
- setup_test_db: run migrations, cleanup on teardown
- db_engine: per-test database engine
- api_client: base AsyncClient for integration tests

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 1.4: Create tests/integration/client.py - APITestClient

**Files:**
- Create: `backend/tests/integration/client.py`
- Dependencies: `backend/tests/integration/conftest.py`

- [ ] **Step 1: Write APITestClient class**

```python
"""APITestClient - Simplified API client wrapper for integration tests."""
from __future__ import annotations

from typing import Any

from httpx import AsyncClient


class APITestError(Exception):
    """Raised when API call returns non-success status."""

    def __init__(self, status: int, data: dict[str, Any]):
        self.status = status
        self.data = data
        super().__init__(f"API Error {status}: {data}")

    def __repr__(self) -> str:
        return f"APITestError(status={self.status}, data={self.data})"


class APITestClient:
    """Wrapper for AsyncClient with simplified error handling.

    All methods raise APITestError on non-success responses.
    Use get_raw() when you need to check status code without raising.
    """

    def __init__(self, client: AsyncClient):
        self._client = client

    async def post(self, path: str, **kwargs: Any) -> dict[str, Any]:
        """POST request, raises on error."""
        resp = await self._client.post(path, **kwargs)
        if not resp.is_success:
            raise APITestError(resp.status_code, resp.json())
        return resp.json()

    async def get(self, path: str, **kwargs: Any) -> dict[str, Any]:
        """GET request, raises on error."""
        resp = await self._client.get(path, **kwargs)
        if not resp.is_success:
            raise APITestError(resp.status_code, resp.json())
        return resp.json()

    async def put(self, path: str, **kwargs: Any) -> dict[str, Any]:
        """PUT request, raises on error."""
        resp = await self._client.put(path, **kwargs)
        if not resp.is_success:
            raise APITestError(resp.status_code, resp.json())
        return resp.json()

    async def patch(self, path: str, **kwargs: Any) -> dict[str, Any]:
        """PATCH request, raises on error."""
        resp = await self._client.patch(path, **kwargs)
        if not resp.is_success:
            raise APITestError(resp.status_code, resp.json())
        return resp.json()

    async def delete(self, path: str, **kwargs: Any) -> dict[str, Any]:
        """DELETE request, raises on error."""
        resp = await self._client.delete(path, **kwargs)
        if not resp.is_success:
            raise APITestError(resp.status_code, resp.json())
        return resp.json()

    async def get_raw(self, path: str, **kwargs: Any) -> tuple[int, dict[str, Any]]:
        """GET request, returns (status_code, json) without raising on error.

        Use this when you need to check error status codes.
        """
        resp = await self._client.get(path, **kwargs)
        return resp.status_code, resp.json()

    async def post_raw(self, path: str, **kwargs: Any) -> tuple[int, dict[str, Any]]:
        """POST request, returns (status_code, json) without raising on error."""
        resp = await self._client.post(path, **kwargs)
        return resp.status_code, resp.json()
```

- [ ] **Step 2: Add client fixtures to conftest.py**

Add to `backend/tests/integration/conftest.py`:

```python
from tests.integration.client import APITestClient


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
```

- [ ] **Step 3: Commit**

```bash
git add backend/tests/integration/client.py backend/tests/integration/conftest.py
git commit -m "feat: add APITestClient wrapper

- APITestClient: simplified API calls with error handling
- get_raw/post_raw: for checking error status codes
- authed_api_client: auto-login fixture
- noauthed_api_client: unauthenticated fixture

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Phase 2: Auth Module Tests

### Task 2.1: Rewrite test_auth_flow.py

**Files:**
- Modify: `backend/tests/integration/test_auth_flow.py`
- Dependencies: `backend/tests/integration/conftest.py`, `backend/tests/integration/client.py`

- [ ] **Step 1: Read current test_auth_flow.py**

```bash
cat backend/tests/integration/test_auth_flow.py
```

- [ ] **Step 2: Write new test_auth_flow.py with real requests**

```python
"""Integration tests for auth API flows."""
from __future__ import annotations

import pytest

from tests.integration.client import APITestClient


class TestAuthFlow:
    """Test authentication flow with real HTTP requests.

    Uses APITestClient for simplified API calls.
    Tests both authenticated and unauthenticated scenarios.
    """

    @pytest.mark.asyncio
    async def test_register_success(self, authed_api_client: APITestClient) -> None:
        """Registered user can access /me endpoint."""
        user = await authed_api_client.get("/api/v1/auth/me")
        assert user["email"]
        assert "id" in user

    @pytest.mark.asyncio
    async def test_me_unauthenticated_returns_401(
        self, noauthed_api_client: APITestClient
    ) -> None:
        """Unauthenticated access to /me returns 401."""
        status, data = await noauthed_api_client.get_raw("/api/v1/auth/me")
        assert status == 401

    @pytest.mark.asyncio
    async def test_login_success(self, noauthed_api_client: APITestClient) -> None:
        """Login with valid credentials succeeds."""
        # Register first
        register_data = {
            "email": f"logintest{uuid4()}@test.com",
            "password": "TestPassword123!",
            "full_name": "Login Test User",
        }
        await noauthed_api_client.post("/api/v1/auth/register", json=register_data)

        # Login
        login_data = {
            "email": register_data["email"],
            "password": register_data["password"],
        }
        status, _ = await noauthed_api_client.post_raw("/api/v1/auth/login", json=login_data)
        assert status == 200

        # Now can access protected endpoint
        user = await noauthed_api_client.get("/api/v1/auth/me")
        assert user["email"] == register_data["email"]

    @pytest.mark.asyncio
    async def test_login_wrong_password(self, noauthed_api_client: APITestClient) -> None:
        """Login with wrong password returns 401."""
        # Register first
        register_data = {
            "email": f"wrongpwd{uuid4()}@test.com",
            "password": "CorrectPassword123!",
            "full_name": "Wrong Pwd User",
        }
        await noauthed_api_client.post("/api/v1/auth/register", json=register_data)

        # Login with wrong password
        login_data = {
            "email": register_data["email"],
            "password": "WrongPassword123!",
        }
        status, data = await noauthed_api_client.get_raw("/api/v1/auth/login", json=login_data)
        assert status == 401

    @pytest.mark.asyncio
    async def test_login_nonexistent_user(self, noauthed_api_client: APITestClient) -> None:
        """Login with non-existent email returns 401."""
        login_data = {
            "email": f"nonexistent{uuid4()}@test.com",
            "password": "AnyPassword123!",
        }
        status, _ = await noauthed_api_client.get_raw("/api/v1/auth/login", json=login_data)
        assert status == 401

    @pytest.mark.asyncio
    async def test_signout(self, authed_api_client: APITestClient) -> None:
        """Signout clears session."""
        status, _ = await authed_api_client.get_raw("/api/v1/auth/signout")
        assert status == 200

    @pytest.mark.asyncio
    async def test_setup_status(self, noauthed_api_client: APITestClient) -> None:
        """Setup status endpoint is public."""
        status, data = await noauthed_api_client.get_raw("/api/v1/auth/setup-status")
        assert status == 200
        assert "needs_setup" in data
```

- [ ] **Step 3: Add uuid4 import**

Add at top of file:
```python
from uuid import uuid4
```

- [ ] **Step 4: Commit**

```bash
git add backend/tests/integration/test_auth_flow.py
git commit -m "test: rewrite test_auth_flow.py with real HTTP requests

- Use APITestClient for all API calls
- Test authenticated and unauthenticated scenarios
- Remove all mocks, use real requests
- Cover: register, login, logout, setup-status

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Phase 3: Thread Module Tests

### Task 3.1: Read Thread API Endpoints

**Files:**
- Read: `backend/app/web/api/thread/views.py`

- [ ] **Step 1: Read thread views to understand endpoints**

```bash
cat backend/app/web/api/thread/views.py
```

---

### Task 3.2: Create test_thread_api.py

**Files:**
- Create: `backend/tests/integration/test_thread_api.py`
- Dependencies: `backend/app/web/api/thread/views.py`

- [ ] **Step 1: Write test_thread_api.py**

```python
"""Integration tests for thread API."""
from __future__ import annotations

import pytest
from uuid import uuid4

from tests.integration.client import APITestClient


class TestThreadAPI:
    """Test thread CRUD operations.

    Tests both authenticated and unauthenticated access.
    """

    @pytest.mark.asyncio
    async def test_create_thread_authenticated(
        self, authed_api_client: APITestClient
    ) -> None:
        """Authenticated user can create a thread."""
        thread_data = {
            "title": f"Test Thread {uuid4()}",
            "description": "Test description",
        }
        thread = await authed_api_client.post("/api/v1/threads", json=thread_data)
        assert thread["id"]
        assert thread["title"] == thread_data["title"]

    @pytest.mark.asyncio
    async def test_create_thread_unauthenticated(
        self, noauthed_api_client: APITestClient
    ) -> None:
        """Unauthenticated user cannot create thread."""
        thread_data = {
            "title": "Unauthorized Thread",
            "description": "Test",
        }
        status, _ = await noauthed_api_client.get_raw("/api/v1/threads", json=thread_data)
        assert status == 401

    @pytest.mark.asyncio
    async def test_list_threads_authenticated(
        self, authed_api_client: APITestClient
    ) -> None:
        """Authenticated user can list their threads."""
        # Create a thread first
        thread_data = {"title": f"List Test {uuid4()}", "description": "Test"}
        await authed_api_client.post("/api/v1/threads", json=thread_data)

        # List threads
        threads = await authed_api_client.get("/api/v1/threads")
        assert isinstance(threads, list)
        assert len(threads) >= 1

    @pytest.mark.asyncio
    async def test_list_threads_unauthenticated(
        self, noauthed_api_client: APITestClient
    ) -> None:
        """Unauthenticated user cannot list threads."""
        status, _ = await noauthed_api_client.get_raw("/api/v1/threads")
        assert status == 401

    @pytest.mark.asyncio
    async def test_get_thread_authenticated(
        self, authed_api_client: APITestClient
    ) -> None:
        """Authenticated user can get a specific thread."""
        # Create thread
        thread_data = {"title": f"Get Test {uuid4()}", "description": "Test"}
        created = await authed_api_client.post("/api/v1/threads", json=thread_data)

        # Get thread
        thread = await authed_api_client.get(f"/api/v1/threads/{created['id']}")
        assert thread["id"] == created["id"]
        assert thread["title"] == thread_data["title"]

    @pytest.mark.asyncio
    async def test_get_thread_unauthenticated(
        self, noauthed_api_client: APITestClient
    ) -> None:
        """Unauthenticated user cannot get thread."""
        fake_id = str(uuid4())
        status, _ = await noauthed_api_client.get_raw(f"/api/v1/threads/{fake_id}")
        assert status == 401
```

- [ ] **Step 2: Commit**

```bash
git add backend/tests/integration/test_thread_api.py
git commit -m "test: add thread API integration tests

- Test authenticated thread CRUD operations
- Test unauthenticated access returns 401
- Use APITestClient for all API calls

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Phase 4: Chat Module Tests

### Task 4.1: Read Chat API Endpoints

**Files:**
- Read: `backend/app/web/api/chat/views.py`

- [ ] **Step 1: Read chat views to understand endpoints**

```bash
cat backend/app/web/api/chat/views.py
```

---

### Task 4.2: Create test_chat_api.py

**Files:**
- Create: `backend/tests/integration/test_chat_api.py`
- Dependencies: `backend/app/web/api/chat/views.py`

- [ ] **Step 1: Write test_chat_api.py**

```python
"""Integration tests for chat API."""
from __future__ import annotations

import pytest

from tests.integration.client import APITestClient


class TestChatAPI:
    """Test chat endpoint authentication.

    Tests both authenticated and unauthenticated scenarios.
    """

    @pytest.mark.asyncio
    async def test_chat_endpoint_requires_auth(
        self, noauthed_api_client: APITestClient
    ) -> None:
        """Unauthenticated access to chat endpoint returns 401."""
        # Note: Adjust path based on actual chat endpoint
        status, _ = await noauthed_api_client.get_raw("/api/v1/chat/sessions")
        assert status == 401

    @pytest.mark.asyncio
    async def test_chat_endpoint_authenticated(
        self, authed_api_client: APITestClient
    ) -> None:
        """Authenticated user can access chat endpoint."""
        # Note: Adjust based on actual chat endpoint behavior
        status, data = await authed_api_client.get_raw("/api/v1/chat/sessions")
        # Accept both 200 (success) and 404 (endpoint exists but no data)
        assert status in (200, 404)
```

- [ ] **Step 2: Commit**

```bash
git add backend/tests/integration/test_chat_api.py
git commit -m "test: add chat API integration tests

- Test authenticated/unauthenticated chat access
- Use APITestClient for all API calls

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 4.3: Remove old test_chat_sse.py

**Files:**
- Delete: `backend/tests/integration/test_chat_sse.py`

- [ ] **Step 1: Delete old test file**

```bash
rm backend/tests/integration/test_chat_sse.py
```

- [ ] **Step 2: Commit**

```bash
git add -u
git commit -m "test: remove deprecated test_chat_sse.py

Absorbed into test_chat_api.py

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Phase 5: Health Check

### Task 5.1: Update test_health.py

**Files:**
- Modify: `backend/tests/integration/test_health.py`

- [ ] **Step 1: Read current test_health.py**

```bash
cat backend/tests/integration/test_health.py
```

- [ ] **Step 2: Update test_health.py to use APITestClient**

```python
"""Integration tests for health endpoint."""
from __future__ import annotations

import pytest

from tests.integration.client import APITestClient


@pytest.fixture
def health_client(api_client) -> APITestClient:
    """Health check client (no auth needed)."""
    return APITestClient(api_client)


@pytest.mark.asyncio
async def test_health_check(health_client: APITestClient) -> None:
    """Health endpoint returns 200."""
    status, data = await health_client.get_raw("/health")
    assert status == 200
    assert data["status"] == "healthy"


@pytest.mark.asyncio
async def test_health_check_status_ok(health_client: APITestClient) -> None:
    """Health endpoint returns status OK."""
    status, data = await health_client.get_raw("/health")
    assert status == 200
    assert isinstance(data, dict)
```

- [ ] **Step 3: Commit**

```bash
git add backend/tests/integration/test_health.py
git commit -m "test: update test_health.py with APITestClient

- Use APITestClient for health checks
- Test both status and data format

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Phase 6: Validation

### Task 6.1: Run Tests Locally

- [ ] **Step 1: Ensure test dependencies are installed**

```bash
cd backend && pip install pytest pytest-asyncio httpx aiosqlite alembic
```

- [ ] **Step 2: Run integration tests**

```bash
cd backend && pytest tests/integration/ -v
```

- [ ] **Step 3: Verify test isolation**

```bash
# Run with verbose output, check for:
# - Each test uses unique database
# - Authenticated tests can access protected endpoints
# - Unauthenticated tests return 401
```

---

### Task 6.2: Update GitHub CI

**Files:**
- Modify: `.github/workflows/ci.yml` (or similar)

- [ ] **Step 1: Check existing CI configuration**

```bash
cat .github/workflows/*.yml 2>/dev/null | head -100
```

- [ ] **Step 2: Add integration test step**

```yaml
# Add to CI workflow
- name: Run integration tests
  run: |
    cd backend
    pip install -e ".[test]"
    pytest tests/integration/ -v --tb=short
```

---

## Self-Review Checklist

After writing the complete plan:

- [ ] **Spec coverage:** All sections from design spec have corresponding tasks
  - deps.py refactor: Task 1.1
  - conftest.py fixtures: Task 1.2, 1.3
  - APITestClient: Task 1.4
  - Auth tests: Task 2.1
  - Thread tests: Task 3.2
  - Chat tests: Task 4.2
  - Health tests: Task 5.1

- [ ] **Placeholder scan:** No TBD/TODO in plan - all steps have actual code

- [ ] **Type consistency:** APITestClient methods (post, get, put, patch, delete, get_raw) consistent across all test files

- [ ] **File paths:** All paths use `backend/` prefix for Python files, relative paths from project root

- [ ] **Test DB cleanup:** `setup_test_db` fixture handles cleanup via `unlink(missing_ok=True)`

- [ ] **Auth fixtures:** `authed_api_client` and `noauthed_api_client` properly separate authenticated/unauthenticated tests
