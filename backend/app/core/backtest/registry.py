"""In-memory backtest ownership registry.

Maps backtest_id → user_id so that only the submitting user
can poll or abort their own backtests.
"""

from __future__ import annotations

from uuid import UUID


class BacktestRegistry:
    """Track which user owns which backtest."""

    def __init__(self) -> None:
        self._owner_map: dict[str, UUID] = {}

    def register(self, backtest_id: str, user_id: UUID) -> None:
        """Record that user_id owns backtest_id."""
        self._owner_map[backtest_id] = user_id

    def is_owner(self, backtest_id: str, user_id: UUID) -> bool:
        """Check if user_id owns the given backtest."""
        owner = self._owner_map.get(backtest_id)
        return owner is not None and owner == user_id

    def remove(self, backtest_id: str) -> None:
        """Remove a backtest from the registry."""
        self._owner_map.pop(backtest_id, None)
