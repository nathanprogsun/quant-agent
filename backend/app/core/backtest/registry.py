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
        self._thread_active: dict[str, str] = {}

    def register(self, backtest_id: str, user_id: UUID, *, thread_id: str | None = None) -> None:
        """Record that user_id owns backtest_id."""
        self._owner_map[backtest_id] = user_id
        if thread_id is not None:
            self._thread_active[thread_id] = backtest_id

    def is_owner(self, backtest_id: str, user_id: UUID) -> bool:
        """Check if user_id owns the given backtest."""
        owner = self._owner_map.get(backtest_id)
        return owner is not None and owner == user_id

    def get_owner(self, backtest_id: str) -> UUID | None:
        """Return the user_id that owns backtest_id, or None."""
        return self._owner_map.get(backtest_id)

    def get_active_for_thread(self, thread_id: str) -> str | None:
        """Return active backtest id for a thread, if any."""
        return self._thread_active.get(thread_id)

    def get_thread_for_active(self, backtest_id: str) -> str | None:
        """Return the thread_id whose active backtest is backtest_id, if any."""
        for thread_id, active_id in self._thread_active.items():
            if active_id == backtest_id:
                return thread_id
        return None

    def release_thread(self, thread_id: str) -> str | None:
        """Clear the active backtest lock for a thread.

        Returns the backtest_id that was active (if any) so the caller can
        also cancel its worker task.
        """
        return self._thread_active.pop(thread_id, None)

    def clear_thread(self, thread_id: str) -> None:
        """Clear active backtest for a thread."""
        self._thread_active.pop(thread_id, None)

    def remove(self, backtest_id: str) -> None:
        """Remove a backtest from the registry."""
        self._owner_map.pop(backtest_id, None)
        self.release_active(backtest_id)

    def release_active(self, backtest_id: str) -> None:
        """Clear thread→backtest lock so the session can submit again.

        Keeps ownership mapping intact so result/detail endpoints still work.
        """
        for thread_id, active_id in list(self._thread_active.items()):
            if active_id == backtest_id:
                self._thread_active.pop(thread_id, None)
