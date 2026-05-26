"""App context - LifeSpanService and AppContext containers."""

from __future__ import annotations

import dataclasses

from httpx import AsyncClient
from langgraph.checkpoint.base import BaseCheckpointSaver

from app.common.runs.manager import RunManager
from app.common.stream_bridge.base import StreamBridge
from app.core.user.service.user_service import UserService
from app.db.dbengine.core import DatabaseEngine


@dataclasses.dataclass(frozen=True)
class LifeSpanService:
    """Container for all application services.

    This is a frozen dataclass holding singleton service instances.
    Each service is injected into FastAPI route handlers via
    get_<service>_from_lifespan() dependency functions.

    Add new services here as frozen fields.
    """

    user_service: UserService | None = dataclasses.field(default=None)


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
    checkpointer: BaseCheckpointSaver | None = None
    stream_bridge: StreamBridge | None = None
    run_manager: RunManager | None = None

    async def close(self) -> None:
        """Close all resources held by the app context."""
        await self.main_db.close()
        await self.http_aclient.aclose()
        if self.stream_bridge:
              await self.stream_bridge.close()
        # InMemorySaver 没有 close() 方法, 但其他实现可能有资源需要清理
        if self.checkpointer and hasattr(self.checkpointer, "close"):
            await self.checkpointer.close()
