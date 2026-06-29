# quant-agent backend Architecture Specification

quant-agent is a layered FastAPI + SQLAlchemy 2.0 async ORM backend following unidirectional dependency and domain-driven design (DDD).

## 1. Architecture Overview

```
┌────────────────────────────────────────────────────────────────────┐
│                             web/                                   │
│  api/ (routes)   middleware/ (auth/exception)   lifespan.py      │
│  application.py   __main__.py   lifespan_service.py               │
├────────────────────────────────────────────────────────────────────┤
│                          app_context/                               │
│                            AppContext                               │
├────────────────────────────────────────────────────────────────────┤
│                             core/                                   │
│  auth/   user/   chat/   backtest/   jq_kb/   generation/        │
│  {domain}/service/  +  types.py                                   │
├────────────────────────────────────────────────────────────────────┤
│                              db/                                    │
│             dao/   +   models/   +   session.py                    │
├────────────────────────────────────────────────────────────────────┤
│                            common/                                  │
│         exception/   runs/   stream_bridge/   serialization/      │
├────────────────────────────────────────────────────────────────────┤
│                             util/                                   │
│      time.py   enum_util.py   pydantic_types/   asyncio_util/    │
│      validation.py   traceback_utils.py                           │
└────────────────────────────────────────────────────────────────────┘
```

- Dependency direction: `web → core → db` (unidirectional), no reverse imports
- Web layer must not directly access `db/dao`
- Core layer must not import `web`
- Cross-layer calls must go through Service or dependency injection

### Anti-patterns quick reference

```python
# ❌ Web layer directly accessing the database
@router.get("/{user_id}")
async def get_user(user_id: UUID, engine=Depends(get_db)):
    result = await engine.one(text("SELECT * FROM users WHERE id=:id"), ...)

# ❌ Core layer handling HTTP concerns
class UserService:
    def get_user(self, request: Request):  # Wrong!
        return request.query_params.get("id")

# ❌ Core layer making external API calls directly
class UserService:
    async def create_user(self, user_data):
        async with httpx.AsyncClient() as client:
            await client.post("https://api.example.com/users", json=user_data)
```

## 2. AppContext & Dependency Injection

- `AppContext` is a `frozen=True` dataclass stored at `app.state.app_context`
- Defined in `app/app_context/app_context.py`, exported via `__init__.py`
- Fields:
  - `session_factory: async_sessionmaker[AsyncSession]` — core dependency, replaces old `DatabaseEngine`
  - `checkpointer: BaseCheckpointSaver[Any] | None` — LangGraph checkpoint backend
  - `stream_bridge: StreamBridge | None` — inter-process streaming bridge
  - `run_manager: RunManager | None` — run lifecycle registry
  - `skill_registry: SkillRegistry | None` — registered agentic skills
  - `lifespan_exit_stack: AsyncExitStack | None` — clean exit stack for checkpointers
- Provides `db` property alias (-> `session_factory`)
- `app_context.close()`: disposes `AsyncEngine`, closes `stream_bridge` and `lifespan_exit_stack`
- Services are instantiated **per-request** via factory functions in `app/web/lifespan_service.py`:
  - `session_from_app_context()` — yields one `AsyncSession` per request; commits on success, rolls back on exception
  - `user_service_from_request(session)` -> `UserService`
  - `thread_service_from_request(session)` -> `ThreadService`
  - `run_service_from_request(app_context)` -> `RunService` (uses `RunManager`, not session)
  - `auth_service_from_request(user_service)` -> `AuthService`
  - `memory_service_from_request(session)` -> `MemoryService`
- Route injection: `Depends(thread_service_from_request)` — no singleton `LifeSpanService` class
- Shared cross-domain dependencies in `web/api/deps.py`: `get_current_user_id`, `get_current_user`
- Lifespan setup: `web/lifespan.py` constructs `AppContext` on startup, calls `close_app_context()` on shutdown

## 3. Data Layer (ORM)

- `Base(DeclarativeBase)` defined in `app/db/models/__init__.py`, shared by all models
- 5 models: `User`, `Thread`, `Run`, `UserMemory`, `MemoryFact`
- Column declarations use `Mapped[T]` + `mapped_column` (SQLAlchemy 2.0 typed style)
- JSON columns: `Run.token_usage`, `MemoryFact.embedding` via `from sqlalchemy import JSON`
- UUID columns: `PG_UUID(as_uuid=True)` (imported from `sqlalchemy.dialects.postgresql`; compiles to `UUID` type under SQLite)
- Soft delete: `Thread.deleted_at` + `Thread.not_deleted()` class method filter
- Audit immunity: `created_at` excluded in `UserRepository.update()`
- **Schema init**: `Base.metadata.create_all()` runs at lifespan startup (no alembic)
- `app/db/session.py`:
  - `make_engine(url, *, echo=False)`
  - `make_session_factory(engine)` -> `async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)`
  - `get_session(session_factory)` dependency function
- Service receives `AsyncSession` as constructor parameter (per-request session managed by `session_from_app_context`)
- Each Service method uses `self.session` and instantiates repository on demand: `UserRepository(self.session)`

## 4. DAO Convention

- Each DAO constructor receives `AsyncSession`: `def __init__(self, session: AsyncSession)`
- Data access via `session.scalar(select(...))`, `session.execute(...)`, `session.get(Model, pk)`
- `find_by_*` returns `Model | None`; `_or_fail` variants (e.g. `find_by_id_and_user_or_fail`) raise `ResourceNotFoundError`
- `IntegrityError` (e.g. duplicate email) -> `ConflictResourceError`: `await self.session.rollback()` then `raise ... from exc`
- ORM uses parameterized queries by default; string concatenation SQL is forbidden
- Repository returns ORM model instances; Service layer converts to DTOs; DAO never returns raw `Row`

### DAO reference structure (`app/db/dao/`)

```
db/dao/
├── __init__.py
├── user_repository.py     # UserRepository - find_by_email, find_by_id, create, update, delete
├── thread_repository.py   # ThreadRepository - soft-delete aware + not_deleted() filter
└── memory_repository.py   # MemoryRepository - UserMemory + MemoryFact two-table operations
```

## 5. Exception System

- `ApplicationError(Exception, ABC)` base class (`app/common/exception/exception.py`)
- 13 subclasses:

| Exception | error_code | HTTP |
|-----------|------------|------|
| `DatabaseError` | `DB_ERROR` | 500 |
| `ConcurrentModificationError` | `CONCURRENT_MODIFICATION` | 409 |
| `ResourceNotFoundError` | `RESOURCE_NOT_FOUND` | 404 |
| `InvalidArgumentError` | `INVALID_ARGUMENT` | 400 |
| `ConflictResourceError` | `CONFLICT` | 409 |
| `IllegalStateError` | `ILLEGAL_STATE` | 500 |
| `ServiceError` | `SERVICE_ERROR` | 500 |
| `UnauthorizedError` | `UNAUTHORIZED` | 401 |
| `ForbiddenError` | `FORBIDDEN` | 403 |
| `ClientError` | `CLIENT_ERROR` | 400 |
| `ExternalServiceError` | `EXTERNAL_SERVICE_ERROR` | 500 (vendor info hidden) |
| `RequestEntityTooLargeError` | `REQUEST_ENTITY_TOO_LARGE` | 413 |
| `UnprocessableEntity` | `UNPROCESSABLE_ENTITY` | 422 |

- `ErrorDetails(code: str, details: str = "", reference_id: str | None = None)` structured payload
- Error codes are `UPPER_SNAKE`
- DAO layer must convert `SQLAlchemyError` / `IntegrityError` to domain exceptions
- Error messages must not contain passwords, tokens, or other sensitive info
- `ApplicationError.to_json_response()` outputs unified envelope: `{"error": {"code", "message", "details"}}`

## 6. Core Convention

- Must not import `web`
- Service class receives `AsyncSession` as constructor parameter (per-request session)
- Transaction boundary managed by `session_from_app_context` — Service does not commit/rollback
- DTO/ORM conversion: `model_config = ConfigDict(from_attributes=True)`
- Domain isolation: `{domain}/types.py` + `{domain}/service/`
- Business domain directories:
  - `auth/` — authentication
  - `user/` — user management
  - `chat/` — chat engine (agent/middlewares/tools/service/skills/memory)
  - `backtest/` — backtesting
  - `jq_kb/` — knowledge base (chunkers/parser/embedding/retrieval)
  - `generation/` — generation service

### Core anti-patterns

```python
# ❌ Service handling HTTP request/Header
class UserService:
    async def create_user(
        self,
        user_id: UUID = Header(...),  # Wrong! HTTP headers don't belong here
    ): ...

# ❌ DTO leaking database internals
class UserDTO(BaseModel):
    id: UUID
    _internal_column: str = None  # Wrong!

# ❌ Business logic in DTO
class UserDTO(BaseModel):
    def authenticate(self, password: str):  # Wrong!
        return self.password_hash == hash(password)
```

## 7. Web Convention

- FastAPI app / routers / middleware / DI live under `app/web/`
- Routes use `APIRouter(prefix="/api/v1/...")`, each domain declares its own prefix
- Route DI accepts only Service (no Repository)
- Every endpoint declares `response_model`
- API interacts with DTOs only; never returns ORM models
- Exceptions handled by registered exception handlers; no `try/except` leaking tracebacks in routes
- Response schemas must never expose `password_hash` / `hashed_password`
- Public paths (`/docs`, `/openapi.json`, `/health`) bypass auth

### Web reference structure

```
web/
├── __main__.py              # uvicorn entry point
├── application.py           # FastAPI app factory (routers + middleware + exception handlers)
├── lifespan.py              # Startup/shutdown: AppContext construction, schema init, cleanup
├── lifespan_service.py      # Per-request DI factory functions (session, services)
├── api/
│   ├── deps.py              # Cross-domain dependencies (get_current_user_id, get_current_user)
│   ├── auth/views.py        # Auth routes (login, register, me, change-password)
│   ├── thread/              # views.py + schema.py + services.py + checkpoint_state.py
│   ├── backtest/            # views.py + schemas.py + stream.py
│   ├── memory/route.py      # Memory routes
│   └── skills/route.py      # Skills routes
└── middleware/
    ├── auth_middleware.py    # Cookie-based JWT auth
    └── exception/exception_handler.py  # ApplicationError + HTTPException + ValidationError handlers
```

## 8. Middleware Convention

- `AuthMiddleware` (`app/web/middleware/auth_middleware.py`):
  - Uses `PUBLIC_PATHS` frozenset to skip public endpoints
  - Parses JWT from `access_token` cookie
  - Sets `request.state.current_user_id` / `current_user_email` / `token_ver`
- Exception handlers registered via `add_exception_handler` in `application.py` (not middleware stack)
- Middleware must NOT write to DB
- Middleware must NOT `try/except` business exceptions (let exception_handler handle them)
- Structured log fields: `http_path`, `http_method`, `http_status`, `error_code`
- 4xx logs at WARNING, 5xx at ERROR
- Do not import business models in middleware; keep cross-cutting concerns clean
- Middleware registration order: CORS -> Auth (`add_middleware` order in `application.py`)

## 9. Models (DB)

- All models inherit `Base(DeclarativeBase)` (defined in `app/db/models/__init__.py`)
- Use `Mapped[T]` + `mapped_column(...)` annotations
- UUID PK: `mapped_column(PG_UUID(as_uuid=True), primary_key=True)` (imported from `sqlalchemy.dialects.postgresql`; compiles to `UUID` under SQLite)
- JSON columns: `mapped_column(JSON)`, e.g. `Run.token_usage`, `MemoryFact.embedding`
- Nullable column ordering: `func.coalesce(Thread.updated_at, Thread.created_at).desc()`
- Models are imported at the end of `app/db/models/__init__.py` (ensures metadata registration order)

### Models anti-patterns

```python
# ❌ Business logic in model
class Organization(Base):
    table_name = "organization"
    def validate(self):  # Wrong!
        pass

# ❌ Wrong column declaration (dict/list won't be recognized as JSON/array)
class Config(Base):
    metadata: dict           # Wrong! use mapped_column(JSON)
    items: list[str]         # Wrong!
```

## 10. Util Rules

- `util/` contains only pure functions: no project module imports, no I/O, no global mutable state
- Files: `time.py`, `enum_util.py`, `pydantic_types/`, `asyncio_util/`, `validation.py`, `traceback_utils.py`
- No business coupling: util must not contain domain rules, read `settings`, or call external APIs

### Util anti-patterns

```python
# ❌ Util depends on other project modules
from app.db.models.user import User  # Wrong!

# ❌ Util with side effects
def generate_id():
    global counter
    counter += 1
    return counter

# ❌ Accessing config from util
def get_db_timeout():
    from app.settings import settings  # Wrong!
    return settings.db_timeout
```

## 11. Testing

- `pytest-asyncio` in auto mode (`asyncio_mode = "auto"` in `pyproject.toml`): no `@pytest.mark.asyncio` needed
- Unit tests: mock at DAO boundary
- Integration tests: `httpx.AsyncClient` + `ASGITransport`, in-process FastAPI app
- DAO unit tests live in `tests/unit/dao/`, use engine + session fixtures, **each test** `drop_all` + `create_all`
- Integration tests use session-scoped `setup_test_db` fixture, calling `Base.metadata.create_all()`
- Test database: `sqlite+aiosqlite:///./test.db` (cleaned per session, kept for inspection)
- Coverage target: 80%
- Unit tests are fully independent, no shared mutable state
- File naming: `test_{module}.py` or `test_{feature}_flow.py`
- Function naming: `test_{function}_{scenario}`

### Test directory structure

```
tests/
├── conftest.py                       # Root config (minimal)
├── unit/
│   ├── conftest.py                   # Unit fixtures
│   └── dao/                          # Repository unit tests
└── integration/
    ├── conftest.py                   # Integration fixtures
    └── test_*_flow.py                # End-to-end flows
```

## 12. Migration Strategy

- **No alembic** (`alembic>=1.13` in `pyproject.toml` is a stale unused dependency; no migration code exists)
- Schema created via `Base.metadata.create_all()` at lifespan startup
- Schema change workflow:
  1. Modify ORM model
  2. Restart application; `create_all` creates new tables but **does not** alter existing ones (SQLite limitation)
- Destructive migration: manually DROP tables or delete `data.db`
- If migrating to Postgres for production, add alembic; current SQLite is for dev/test only

## Data Flow (Complete Call Chain)

```
HTTP Request
    |
web/api/{domain}/views.py          (Pydantic validation, response_model)
    |
core/{domain}/service/*.py         (Business orchestration, DTO conversion)
    |
db/dao/{domain}_repository.py      (ORM session operations)
    |
db/models/{domain}.py              (DeclarativeBase model)
    |
AsyncEngine (sqlite | postgres)
```
