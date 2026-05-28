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
│   ├── test_auth_flow.py                # Auth flow tests
│   ├── test_health.py
│   └── test_chat_sse.py
└── unit/
    ├── __init__.py
    └── conftest.py
```

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
| `client` | Base AsyncClient, unauthenticated |
| `authed_client` | Auto-login, returns (client, user) |
| `noauthed_client` | Explicit unauthenticated client |

```python
@pytest.fixture
async def client(setup_test_db) -> AsyncGenerator[AsyncClient, None]:
    app = get_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

@pytest.fixture
async def authed_client(client: AsyncClient) -> tuple[AsyncClient, dict]:
    """Auto-login and return client with cookies set."""
    resp = await client.post("/api/v1/auth/register", json={
        "email": f"{uuid4()}@test.com",
        "password": "TestPassword123!",
        "full_name": "Test User"
    })
    assert resp.status_code == 201
    me_resp = await client.get("/api/v1/auth/me")
    return client, me_resp.json()

@pytest.fixture
async def noauthed_client(client: AsyncClient) -> AsyncClient:
    """Client without authentication."""
    return client
```

## APITestClient

Wrapper for simplified API calls with error handling.

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
```

## Test Cases

### Auth Flow Tests

```python
class TestAuthFlow:
    async def test_register_success(self, authed_client):
        """Registered user can access /me."""
        client, user = authed_client
        assert user["email"]

    async def test_me_unauthenticated_returns_401(self, noauthed_client):
        """Unauthenticated access to /me returns 401."""
        resp = await noauthed_client.get("/api/v1/auth/me")
        assert resp.status_code == 401

    async def test_login_success(self, noauthed_client):
        """Login with valid credentials."""
        # Register first
        await noauthed_client.post("/api/v1/auth/register", json={...})
        # Login
        resp = await noauthed_client.post("/api/v1/auth/login", json={...})
        assert resp.status_code == 200
        # Now can access protected endpoint
        me = await noauthed_client.get("/api/v1/auth/me")
        assert me.status_code == 200

    async def test_login_wrong_password(self, noauthed_client):
        """Login with wrong password returns 401."""
        resp = await noauthed_client.post("/api/v1/auth/login", json={
            "email": "test@example.com",
            "password": "wrong"
        })
        assert resp.status_code == 401
```

## GitHub CI Compatibility

- Use `/tmp/test_{uuid}.db` for ephemeral filesystem
- Each job uses unique database
- Alembic migrations run via Python (not external process)
- Works with any CI that supports Python + SQLite

## Implementation Checklist

- [ ] Refactor `deps.py` - remove `HTTPBearer`, add `get_current_user_id`
- [ ] Update `conftest.py` - add test database fixtures
- [ ] Create `integration/conftest.py` - client fixtures
- [ ] Create `integration/client.py` - APITestClient
- [ ] Rewrite `test_auth_flow.py` - real requests + auth state tests
- [ ] Update `test_health.py` - use new fixtures
- [ ] Update `test_chat_sse.py` - use new fixtures
- [ ] Run tests locally - verify isolation
- [ ] Run tests in CI - verify compatibility
