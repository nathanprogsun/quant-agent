"""Memory provider for DynamicContextMiddleware injection (P4.2).

Fetches a user's memory/facts from Postgres via MemoryService and builds a
token-budgeted ``<memory>`` block. The middleware consumes this as
``HumanMessage(id='{stable_id}__memory')``.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Protocol
from uuid import UUID

from app.core.chat.memory.block import build_memory_block
from app.core.chat.memory.service import MemoryService

if TYPE_CHECKING:
    from app.config.memory_config import MemoryConfig

logger = logging.getLogger(__name__)


class SessionFactoryProtocol(Protocol):
    def __call__(self) -> Any: ...


class MemoryProvider:
    """Resolves a user's memory block for injection."""

    def __init__(
        self,
        session_factory: SessionFactoryProtocol,
        config: MemoryConfig,
    ) -> None:
        self._session_factory = session_factory
        self._config = config

    async def get_block(self, user_id: UUID | str | None) -> str | None:
        """Return the ``<memory>`` block for ``user_id``, or None."""
        if user_id is None:
            return None
        try:
            uid = UUID(str(user_id))
        except (ValueError, TypeError):
            logger.debug("Memory provider: invalid user_id %r", user_id)
            return None
        try:
            async with self._session_factory() as session:
                service = MemoryService(session)
                ctx = await service.get_user_memory(uid)
                return build_memory_block(ctx.memories, ctx.facts, self._config)
        except Exception:
            logger.exception("Memory provider failed for user %s", uid)
            return None


# ---- Module-level singleton wiring (set during app lifespan) ----

_global_provider: MemoryProvider | None = None


def set_memory_provider(provider: MemoryProvider | None) -> None:
    global _global_provider
    _global_provider = provider


def get_memory_provider() -> MemoryProvider | None:
    return _global_provider


__all__ = ["MemoryProvider", "get_memory_provider", "set_memory_provider"]
