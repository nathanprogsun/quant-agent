"""App context - LifeSpanService and AppContext containers."""

from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from httpx import AsyncClient

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

    async def close(self) -> None:
        """Close all resources held by the app context."""
        await self.main_db.close()
        await self.http_aclient.aclose()
