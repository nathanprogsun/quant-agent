# Integration Test Redesign Design

## Status

- Date: 2026-05-28
- Approved: Yes

## Overview

Redesign quant-agent integration tests to follow salestech-be patterns with proper authentication (cookie-based) and test isolation.

## Authentication Mechanism

### Current Problem

- `deps.py` uses `HTTPBearer` (reads Authorization header)
- `AuthMiddleware` uses cookie (`access_token` cookie)
- Inconsistent authentication mechanisms

### Solution

**Remove `HTTPBearer` dependency, use cookie-based auth only via `AuthMiddleware`.**

```python
# deps.py - get_current_user
def get_current_user(request: Request) -> str:
    """Get current user ID from request state set by AuthMiddleware."""
    user_id = getattr(request.state, "current_user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="未认证")
    return user_id
```

**Rationale**: `AuthMiddleware` already validates the token and sets `request.state.current_user_id`. No need to re-validate in dependency.

## Test Structure

```
tests/
├── conftest.py                          # Root fixtures
├── integration/
│   ├── __init__.py
│   ├── conftest.py                      # Test DB, client fixtures
│   ├── client.py                        # APITestClient wrapper
│   ├── test_auth_flow.py                # Auth API tests
│   ├── test_thread_api.py               # Thread API tests
│   ├── test_chat_api.py                # Chat API tests
│   └── test_health.py
└── unit/
    ├── __init__.py
    └── conftest.py
```

## API Modules Coverage

| Module | Endpoints | Tests |
|--------|-----------|-------|
| `auth` | `/login`, `/register`, `/me`, `/signout` | `test_auth_flow.py` |
| `thread` | Thread CRUD endpoints | `test_thread_api.py` |
| `chat` | Chat/SSE endpoints | `test_chat_api.py` |

## Fixtures Design

### Test Database Isolation

| Fixture | Scope | Purpose |
|---------|-------|---------|
| `alembic_cfg` | session | Alembic configuration |
| `test_db_url` | session | Unique test DB URL per session |
| `setup_test_db` | session | Run migrations, yield URL, cleanup |
| `test_engine` | function | Create engine for each test |

```python
# conftest.py
@pytest.fixture(scope="session")
def test_db_url():
    db_name = f"test_{uuid4()[:8]}.db"
    return f"sqlite+aiosqlite:///{db_name}"

@pytest.fixture(scope="session")
def setup_test_db(alembic_cfg, test_db_url):
    alembic_cfg.config.set_main_option("sqlalchemy.url", test_db_url)
    command.upgrade(alembic_cfg, "head")
    yield test_db_url
    Path(test_db_url.replace("sqlite+aiosqlite:///", "")).unlink(missing_ok=True)
```

### Client Fixtures

| Fixture | Purpose |
|---------|---------|
| `api_client` | Base AsyncClient, unauthenticated |
| `authed_api_client` | Auto-login, returns APITestClient with cookies |
| `noauthed_api_client` | Explicit unauthenticated APITestClient |

```python
@pytest.fixture
async def api_client(setup_test_db) -> AsyncGenerator[AsyncClient, None]:
    app = get_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

@pytest.fixture
async def authed_api_client(api_client: AsyncClient) -> APITestClient:
    """Auto-login and return APITestClient with cookies set."""
    client = APITestClient(api_client)
    await client.post("/api/v1/auth/register", json={
        "email": f"{uuid4()}@test.com",
        "password": "TestPassword123!",
        "full_name": "Test User"
    })
    return client

@pytest.fixture
async def noauthed_api_client(api_client: AsyncClient) -> APITestClient:
    """APITestClient without authentication."""
    return APITestClient(api_client)
```

## APITestClient

Wrapper for simplified API calls with error handling. **All tests should use APITestClient, not raw AsyncClient.**

```python
class APITestError(Exception):
    def __init__(self, status: int, data: dict):
        self.status = status
        self.data = data

class APITestClient:
    def __init__(self, client: AsyncClient):
        self._client = client

    async def post(self, path: str, **kwargs) -> dict:
        resp = await self._client.post(path, **kwargs)
        if not resp.is_success:
            raise APITestError(resp.status_code, resp.json())
        return resp.json()

    async def get(self, path: str, **kwargs) -> dict:
        resp = await self._client.get(path, **kwargs)
        if not resp.is_success:
            raise APITestError(resp.status_code, resp.json())
        return resp.json()

    async def put(self, path: str, **kwargs) -> dict:
        resp = await self._client.put(path, **kwargs)
        if not resp.is_success:
            raise APITestError(resp.status_code, resp.json())
        return resp.json()

    async def patch(self, path: str, **kwargs) -> dict:
        resp = await self._client.patch(path, **kwargs)
        if not resp.is_success:
            raise APITestError(resp.status_code, resp.json())
        return resp.json()

    async def delete(self, path: str, **kwargs) -> dict:
        resp = await self._client.delete(path, **kwargs)
        if not resp.is_success:
            raise APITestError(resp.status_code, resp.json())
        return resp.json()

    async def get_raw(self, path: str, **kwargs) -> tuple[int, dict]:
        """Return raw response for status code checking."""
        resp = await self._client.get(path, **kwargs)
        return resp.status_code, resp.json()
```

## Test Cases

### Auth Flow Tests (`test_auth_flow.py`)

```python
class TestAuthFlow:
    async def test_register_success(self, authed_api_client: APITestClient):
        """Registered user can access /me."""
        user = await authed_api_client.get("/api/v1/auth/me")
        assert user["email"]

    async def test_me_unauthenticated_returns_401(self, noauthed_api_client: APITestClient):
        """Unauthenticated access to /me returns 401."""
        status, _ = await noauthed_api_client.get_raw("/api/v1/auth/me")
        assert status == 401

    async def test_login_success(self, noauthed_api_client: APITestClient):
        """Login with valid credentials."""
        # Register first
        await noauthed_api_client.post("/api/v1/auth/register", json={...})
        # Login
        await noauthed_api_client.post("/api/v1/auth/login", json={...})
        # Now can access protected endpoint
        user = await noauthed_api_client.get("/api/v1/auth/me")
        assert user["email"]

    async def test_login_wrong_password(self, noauthed_api_client: APITestClient):
        """Login with wrong password returns 401."""
        status, _ = await noauthed_api_client.get_raw("/api/v1/auth/login", json={
            "email": "test@example.com",
            "password": "wrong"
        })
        assert status == 401
```

### Thread API Tests (`test_thread_api.py`)

```python
class TestThreadAPI:
    async def test_create_thread_authenticated(self, authed_api_client: APITestClient):
        """Authenticated user can create thread."""
        thread = await authed_api_client.post("/api/v1/threads", json={...})
        assert thread["id"]

    async def test_create_thread_unauthenticated(self, noauthed_api_client: APITestClient):
        """Unauthenticated user cannot create thread."""
        status, _ = await noauthed_api_client.get_raw("/api/v1/threads")
        assert status == 401

    async def test_list_threads_authenticated(self, authed_api_client: APITestClient):
        """Authenticated user can list their threads."""
        threads = await authed_api_client.get("/api/v1/threads")
        assert isinstance(threads, list)
```

### Chat API Tests (`test_chat_api.py`)

```python
class TestChatAPI:
    async def test_chat_endpoint_requires_auth(self, noauthed_api_client: APITestClient):
        """Unauthenticated access to chat returns 401."""
        status, _ = await noauthed_api_client.get_raw("/api/v1/chat/...")
        assert status == 401

    async def test_chat_endpoint_authenticated(self, authed_api_client: APITestClient):
        """Authenticated user can access chat endpoint."""
        response = await authed_api_client.get("/api/v1/chat/...")
        assert response is not None
```

## GitHub CI Compatibility

- Use `/tmp/test_{uuid}.db` for ephemeral filesystem
- Each job uses unique database
- Alembic migrations run via Python (not external process)
- Works with any CI that supports Python + SQLite

## Implementation Checklist

### Phase 1: Core Infrastructure
- [ ] Refactor `deps.py` - remove `HTTPBearer`, use cookie-based `get_current_user_id`
- [ ] Create `tests/conftest.py` - root fixtures (settings override)
- [ ] Create `tests/integration/conftest.py` - test DB + client fixtures
- [ ] Create `tests/integration/client.py` - APITestClient

### Phase 2: Auth Module
- [ ] Rewrite `test_auth_flow.py` - real requests + auth state tests (APITestClient)

### Phase 3: Thread Module
- [ ] Create `test_thread_api.py` - thread API tests (APITestClient)

### Phase 4: Chat Module
- [ ] Create `test_chat_api.py` - chat API tests (APITestClient)
- [ ] Deprecate `test_chat_sse.py` (absorbed into `test_chat_api.py`)

### Phase 5: Health Check
- [ ] Update `test_health.py` - use new fixtures (APITestClient)

### Phase 6: Validation
- [ ] Run tests locally - verify isolation
- [ ] Run tests in CI - verify compatibility
