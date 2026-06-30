"""Subagent concurrency limit middleware (P3.6).

Replaces the prior name-substring counter with a lookup of
``_subagent_usage_cache.size()`` so the limit is driven by real subagent
traffic (token-usage bookkeeping), not heuristic tool-name substring
matching. The cache is populated by ``TaskTool`` on terminal status and
consumed by ``TokenUsageMiddleware`` (P3.4 bridge).

The limit is clamped to ``[MIN_SUBAGENT_LIMIT, MAX_SUBAGENT_LIMIT] = [2, 4]``
(``MAX_CONCURRENT_SUBAGENTS = 3`` default), matching the deer-flow
subagent_limit_middleware.py:11-39 contract.
"""

from __future__ import annotations

import logging
from typing import Any

from app.core.chat.middlewares.base import AgentMiddleware
from app.core.chat.tools.builtin.task_tool import _subagent_usage_cache

logger = logging.getLogger(__name__)

MIN_SUBAGENT_LIMIT = 2
MAX_SUBAGENT_LIMIT = 4
MAX_CONCURRENT_SUBAGENTS = 3


def _clamp_subagent_limit(value: int) -> int:
    """Clamp ``value`` into ``[MIN_SUBAGENT_LIMIT, MAX_SUBAGENT_LIMIT]``."""
    return max(MIN_SUBAGENT_LIMIT, min(MAX_SUBAGENT_LIMIT, value))


def _active_subagent_count() -> int:
    """Read the current size of ``task_tool._subagent_usage_cache``."""
    return len(_subagent_usage_cache)


class SubagentLimitMiddleware(AgentMiddleware):
    """Limits concurrent subagent calls using the real usage-cache size.

    This middleware reads ``task_tool._subagent_usage_cache`` size in
    ``before_model`` and reports ``subagent_limit_reached=True`` when the
    count is at-or-above ``max_concurrent``. Callers (lead_agent, the
    service layer) consult this flag to react.
    """

    def __init__(self, max_concurrent: int = MAX_CONCURRENT_SUBAGENTS) -> None:
        """Initialize with a clamped concurrency limit.

        Args:
            max_concurrent: Maximum concurrent subagent calls allowed.
                Defaults to ``MAX_CONCURRENT_SUBAGENTS`` (3). Clamped to
                ``[MIN_SUBAGENT_LIMIT, MAX_SUBAGENT_LIMIT]``.
        """
        self._max_concurrent = _clamp_subagent_limit(max_concurrent)
        # Legacy attribute — kept for backward-compat callers but no longer
        # mutated by the heuristic path.
        self._active_subagents = 0

    async def before_model(
        self, state: dict[str, Any], config: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Before model — check the cache size against the concurrency limit."""
        active = _active_subagent_count()
        self._active_subagents = active
        if active >= self._max_concurrent:
            logger.warning(
                "Subagent concurrency limit reached: active=%d, max=%d",
                active,
                self._max_concurrent,
            )
            return {
                "subagent_limit_reached": True,
                "max_concurrent": self._max_concurrent,
            }
        return None

    async def before_tool(
        self, tool_name: str, tool_input: dict[str, Any], config: dict[str, Any]
    ) -> dict[str, Any] | None:
        """No-op — the limit is driven by the cache, not tool_name substrings."""
        return None

    async def after_tool(
        self, tool_name: str, tool_input: dict[str, Any], result: Any, config: dict[str, Any]
    ) -> Any | None:
        """No-op — see ``before_tool``."""
        return None

    def get_active_count(self) -> int:
        """Return the live concurrency count (used by the limit gate)."""
        return _active_subagent_count()

    def get_limit(self) -> int:
        """Return the maximum concurrent subagent limit."""
        return self._max_concurrent
