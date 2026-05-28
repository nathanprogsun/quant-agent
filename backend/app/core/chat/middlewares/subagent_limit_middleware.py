"""Subagent limit middleware."""

from __future__ import annotations

import asyncio
from typing import Any

from app.core.chat.middlewares.base import AgentMiddleware


class SubagentLimitMiddleware(AgentMiddleware):
    """Limits concurrent subagent calls.

    Prevents resource exhaustion by limiting how many subagents
    can be spawned simultaneously.
    """

    def __init__(self, max_concurrent_subagents: int = 3) -> None:
        """Initialize subagent limit.

        Args:
            max_concurrent_subagents: Maximum concurrent subagent calls allowed.
        """
        self._max_concurrent = max_concurrent_subagents
        self._semaphore: asyncio.Semaphore | None = None
        self._active_subagents = 0

    def _get_semaphore(self) -> asyncio.Semaphore:
        """Get or create semaphore (lazy initialization)."""
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(self._max_concurrent)
        return self._semaphore

    async def before_model(self, state: dict[str, Any], config: dict[str, Any]) -> dict[str, Any] | None:
        """Before model - check subagent limit."""
        if self._active_subagents >= self._max_concurrent:
            return {
                "subagent_limit_reached": True,
                "max_concurrent": self._max_concurrent,
            }
        return None

    async def before_tool(self, tool_name: str, tool_input: dict[str, Any], config: dict[str, Any]) -> dict[str, Any] | None:
        """Before tool - increment active count if subagent-related."""
        # Detect subagent tools by naming convention
        is_subagent = tool_name.lower().startswith("subagent") or tool_name.lower().endswith("subagent")
        if is_subagent:
            self._active_subagents += 1
        return None

    async def after_tool(
        self, tool_name: str, tool_input: dict[str, Any], result: Any, config: dict[str, Any]
    ) -> Any | None:
        """After tool - decrement active count if subagent-related."""
        is_subagent = tool_name.lower().startswith("subagent") or tool_name.lower().endswith("subagent")
        if is_subagent and self._active_subagents > 0:
            self._active_subagents -= 1
        return None

    def get_active_count(self) -> int:
        """Return number of currently active subagents."""
        return self._active_subagents

    def get_limit(self) -> int:
        """Return the maximum concurrent subagent limit."""
        return self._max_concurrent
