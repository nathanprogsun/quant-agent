"""App context - AppContext container and helper utilities."""

from __future__ import annotations

import dataclasses
from contextlib import AsyncExitStack
from typing import Any, Literal

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.common.runs.manager import RunManager
from app.common.stream_bridge.base import StreamBridge
from app.core.backtest.registry import BacktestRegistry
from app.core.chat.skills.registry import SkillRegistry


async def create_checkpointer(
    exit_stack: AsyncExitStack,
    *,
    backend: Literal["memory", "sqlite", "postgres"] = "sqlite",
    connection_string: str = "checkpoints.db",
) -> BaseCheckpointSaver[Any]:
    """Enter a checkpointer context on ``exit_stack`` for the app lifetime."""
    if backend == "sqlite":
        return await exit_stack.enter_async_context(
            AsyncSqliteSaver.from_conn_string(connection_string),
        )
    if backend == "memory":
        return InMemorySaver()
    msg = f"Checkpointer backend {backend!r} is not implemented"
    raise NotImplementedError(msg)


@dataclasses.dataclass(frozen=True)
class AppContext:
    """Application Context container.

    Holds the main session factory and shared HTTP client.
    Stored in app.state.app_context for retrieval via
    get_session_factory() and get_http_aclient() dependencies.

    NOTE: Thread-safe frozen dataclass. Avoid using shared mutable state.
    """

    session_factory: async_sessionmaker[AsyncSession]
    checkpointer: BaseCheckpointSaver[Any] | None = None
    stream_bridge: StreamBridge | None = None
    run_manager: RunManager | None = None
    skill_registry: SkillRegistry | None = None
    backtest_registry: BacktestRegistry | None = None
    lifespan_exit_stack: AsyncExitStack | None = dataclasses.field(
        default=None,
        compare=False,
        repr=False,
    )

    @property
    def db(self) -> async_sessionmaker[AsyncSession]:
        """Alias for session_factory — keeps old call sites working."""
        return self.session_factory

    async def close(self) -> None:
        """Close all resources held by the app context."""
        # AsyncEngine is disposed via the session_factory's bound engine
        if self.session_factory is not None:
            await self.session_factory.kw["bind"].dispose()
        if self.stream_bridge:
            await self.stream_bridge.close()
        if self.lifespan_exit_stack is not None:
            await self.lifespan_exit_stack.aclose()
        elif self.checkpointer is not None and hasattr(self.checkpointer, "close"):
            await self.checkpointer.close()
