"""App context - LifeSpanService and AppContext containers."""

from __future__ import annotations

import dataclasses
from contextlib import AsyncExitStack
from typing import Any, Literal

from httpx import AsyncClient
from langgraph.checkpoint.base import BaseCheckpointSaver

from app.common.runs.manager import RunManager
from app.common.stream_bridge.base import StreamBridge
from app.core.auth.service.auth_service import AuthService
from app.core.chat.service.thread_service import ThreadService
from app.core.user.service.user_service import UserService
from app.db.dbengine.core import DatabaseEngine


async def create_checkpointer(
    exit_stack: AsyncExitStack,
    *,
    backend: Literal["memory", "sqlite", "postgres"] = "sqlite",
    connection_string: str = "checkpoints.db",
) -> BaseCheckpointSaver[Any]:
    """Enter a checkpointer context on ``exit_stack`` for the app lifetime."""
    if backend == "sqlite":
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

        return await exit_stack.enter_async_context(
            AsyncSqliteSaver.from_conn_string(connection_string),
        )

    if backend == "memory":
        from langgraph.checkpoint.memory import InMemorySaver

        return InMemorySaver()

    msg = f"Checkpointer backend {backend!r} is not implemented"
    raise NotImplementedError(msg)


@dataclasses.dataclass(frozen=True)
class LifeSpanService:
    """Container for all application services.

    This is a frozen dataclass holding singleton service instances.
    Each service is injected into FastAPI route handlers via
    get_<service>_from_lifespan() dependency functions.

    Add new services here as frozen fields.
    """

    auth_service: AuthService | None = None
    user_service: UserService | None = None
    thread_service: ThreadService | None = None


@dataclasses.dataclass(frozen=True)
class AppContext:
    """Application Context container.

    Holds the main database engine and shared HTTP client.
    Stored in app.state.app_context for retrieval via
    get_db_engine() and get_http_aclient() dependencies.

    NOTE: Thread-safe frozen dataclass. Avoid using shared mutable state.
    """

    main_db: DatabaseEngine
    http_aclient: AsyncClient
    lifespan_service: LifeSpanService
    checkpointer: BaseCheckpointSaver[Any] | None = None
    stream_bridge: StreamBridge | None = None
    run_manager: RunManager | None = None
    lifespan_exit_stack: AsyncExitStack | None = dataclasses.field(
        default=None,
        compare=False,
        repr=False,
    )

    async def close(self) -> None:
        """Close all resources held by the app context."""
        await self.main_db.close()
        await self.http_aclient.aclose()
        if self.stream_bridge:
            await self.stream_bridge.close()
        if self.lifespan_exit_stack is not None:
            await self.lifespan_exit_stack.aclose()
        elif self.checkpointer is not None and hasattr(self.checkpointer, "close"):
            await self.checkpointer.close()
