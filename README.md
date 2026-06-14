# Quant Agent

An AI-powered conversational platform for quantitative investment research. Analyze markets, generate strategy code, run backtests, and get improvement suggestions — all through natural language dialogue.

## Features

- **Multi-turn Dialogue** — LangGraph-based agent orchestration with context memory and multi-step reasoning
- **Streaming Responses** — Real-time SSE push, token-by-token output, with automatic reconnection
- **Session Management** — Create / list / delete conversations, auto-generated titles
- **User Authentication** — JWT cookie auth, CSRF protection, first-deploy guided setup
- **Middleware Architecture** — Extensible middleware chain (title generation, context compression, token counting, etc.)
- **Tool Calling** — Agent can invoke external tools (search, code execution, data queries, etc.)
- **Skill System** — Compose multiple tools into reusable skills, with SubAgent parallel execution

## Tech Stack

**Backend:** Python 3.11+ · FastAPI · LangGraph · SQLAlchemy (async) · JWT

**Frontend:** Next.js 16 · React 19 · TypeScript 5 · Tailwind CSS 4 · TanStack Query · Zustand

**Infrastructure:** SQLite (dev) / PostgreSQL (prod) · LangGraph Checkpointer

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 20+
- pnpm 10+
- uv (Python package manager)

### Backend

```bash
cd backend

# Install dependencies
uv sync

# Configure environment
cp .env.example .env
# Edit .env: set JWT_SECRET_KEY, LLM_API_KEY, LLM_API_BASE, etc.

# Run database migrations
uv run alembic upgrade head

# Start dev server
uv run uvicorn app.web.application:app --reload --port 8000
```

### Frontend

```bash
cd frontend

# Install dependencies
pnpm install

# Configure environment
echo "BACKEND_URL=http://localhost:8000" > .env.local

# Start dev server
pnpm dev
```

Open http://localhost:3000. On first deployment, you'll be redirected to `/setup` to create an admin account.

### VSCode

Two debug configurations are provided in `.vscode/launch.json`:

- **Python: FastAPI Backend** — Backend debugger on port 8000
- **Next.js: Frontend Dev** — Frontend debugger with Chrome auto-open

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│  Frontend (Next.js)                                      │
│  /workspace/chats/[id]   Chat interface                  │
│  /setup                  First-time admin setup          │
│  /login                  Authentication                  │
├──────────────────────────────────────────────────────────┤
│  API Gateway (FastAPI)                                   │
│  /api/v1/auth/*          Authentication endpoints        │
│  /api/v1/threads/*       Conversation CRUD               │
│  /api/v1/chat/*          Chat + SSE streaming            │
├──────────────────────────────────────────────────────────┤
│  Core (Business Logic)                                   │
│  auth/                   User authentication             │
│  user/                   User management                 │
│  chat/                   Agent orchestration             │
│    agent/                LangGraph StateGraph factory    │
│    middlewares/           Middleware chain                │
│    service/              Thread & chat services          │
├──────────────────────────────────────────────────────────┤
│  Common (Infrastructure)                                 │
│  stream_bridge/          SSE event pub/sub               │
│  runs/                   Run lifecycle management        │
├──────────────────────────────────────────────────────────┤
│  Database (Persistence)                                  │
│  models/                 ORM models                      │
│  dao/                    Repository pattern              │
│  migrations/             Alembic migrations              │
└──────────────────────────────────────────────────────────┘
```

## Project Structure

```
quant-agent/
├── backend/
│   ├── app/
│   │   ├── app_context/          # Dependency injection container
│   │   ├── common/               # Shared infrastructure
│   │   │   ├── exception/        # Exception definitions
│   │   │   ├── stream_bridge/    # SSE event bridge
│   │   │   └── runs/             # Run manager
│   │   ├── core/                 # Business domains
│   │   │   ├── auth/             # Authentication
│   │   │   ├── user/             # User management
│   │   │   └── chat/             # Chat domain
│   │   │       ├── agent/        # LangGraph agent factory
│   │   │       ├── middlewares/   # Middleware chain
│   │   │       └── service/      # Business services
│   │   ├── db/                   # Data access layer
│   │   │   ├── dao/              # Repositories
│   │   │   ├── models/           # ORM models
│   │   │   └── migrations/       # Alembic migrations
│   │   └── web/                  # API layer
│   │       ├── api/              # Route handlers
│   │       ├── middleware/        # HTTP middleware
│   │       └── lifespan.py       # App lifecycle
│   └── tests/
│       ├── unit/                 # Unit tests
│       └── integration/          # Integration tests
│
├── frontend/
│   └── src/
│       ├── app/                  # Next.js App Router
│       │   ├── (auth)/           # Login / setup pages
│       │   ├── api/              # API proxy routes
│       │   └── workspace/        # Main workspace
│       ├── components/           # React components
│       ├── core/                 # Business logic
│       │   ├── api/              # LangGraph SDK client
│       │   ├── auth/             # Auth (SSR + client)
│       │   ├── threads/          # Thread management
│       │   └── messages/         # Message processing
│       ├── hooks/                # Shared hooks
│       └── lib/                  # Shared utilities
│
└── .vscode/                      # Debug configurations
```

## API Reference

### Authentication

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| POST | `/api/v1/auth/register` | Register new user | No |
| POST | `/api/v1/auth/login` | Login | No |
| POST | `/api/v1/auth/initialize` | Create first admin (one-time) | No |
| GET | `/api/v1/auth/setup-status` | Check if system needs setup | No |
| GET | `/api/v1/auth/me` | Get current user | Yes |
| GET | `/api/v1/auth/signout` | Logout | No |
| POST | `/api/v1/auth/change-password` | Change password | Yes |
| POST | `/api/v1/auth/refresh` | Refresh token | No |

### Threads

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/threads` | List threads |
| POST | `/api/v1/threads` | Create thread |
| GET | `/api/v1/threads/{id}` | Get thread |
| PATCH | `/api/v1/threads/{id}` | Update thread |
| DELETE | `/api/v1/threads/{id}` | Delete thread |

### Chat

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/chat/{thread_id}/runs/stream` | Create run + SSE stream |
| POST | `/api/v1/chat/{thread_id}/runs/{run_id}/cancel` | Cancel run |

### SSE Event Format

```
event: metadata
data: {"run_id":"uuid","thread_id":"uuid"}

event: messages
data: {"content":[{"type":"text","text":"Hello"}],"type":"ai","id":"msg-1"}

event: values
data: {"messages":[...],"title":"Auto-generated title"}

event: error
data: {"error":"Error message"}

event: end
data: null

: heartbeat
```

## Configuration

### Backend (`.env`)

```bash
# Authentication
JWT_SECRET_KEY=your-secret-key
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=10080

# LLM
LLM_API_KEY=your-api-key
LLM_API_BASE=https://api.openai.com/v1
DEFAULT_MODEL=gpt-4o

# Database
DATABASE_URL=sqlite+aiosqlite:///./quant_agent.db

# Checkpointer
CHECKPOINTER_BACKEND=sqlite
CHECKPOINTER_CONNECTION_STRING=checkpoints.db
```

### Frontend (`.env.local`)

```bash
# Backend API URL (used by SSR proxy routes)
BACKEND_URL=http://localhost:8000
```

## Testing

```bash
# Backend unit tests
cd backend && uv run pytest tests/unit/ -v

# Backend integration tests
cd backend && uv run pytest tests/integration/ -v

# Frontend type check
cd frontend && npx tsc --noEmit

# Frontend unit tests
cd frontend && pnpm test
```

## Documentation

PRD、实施计划与 task spec 存放在本地 `docs/` 目录，**不纳入本 Git 仓库**（见 `.gitignore`）。在完整工作区中打开 `docs/README.md` 查看索引。

## Roadmap

| Status | Focus |
|--------|-------|
| Done | Core chat (Agent + SSE + Auth + Thread CRUD) |
| In Progress | Middleware chain + Tools + Multi-model |
| Planned | Skill system + File upload + Memory |
| Planned | Plan mode + Artifacts + Custom agents |

## Contributing

Contributions are welcome! Please open an issue first to discuss what you'd like to change.

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/my-feature`)
3. Commit your changes (`git commit -m 'feat: add my feature'`)
4. Push to the branch (`git push origin feature/my-feature`)
5. Open a Pull Request

## Getting Help

- Open an [issue](../../issues) for bug reports or feature requests
- Check existing issues before filing a new one

## License

MIT
