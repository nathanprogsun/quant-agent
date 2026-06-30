"""Loop detection middleware."""

from __future__ import annotations

from typing import Any

from langchain.agents.middleware import AgentMiddleware


class LoopDetectionMiddleware(AgentMiddleware):
    """Detects repeated tool call patterns.

    Tracks tool call sequences and flags when a loop is detected
    (same tool called N times in a row or same pattern repeated).
    """

    def __init__(self, max_repeated_calls: int = 3, max_sequence_length: int = 5) -> None:
        """Initialize loop detection.

        Args:
            max_repeated_calls: Maximum times the same tool can be called consecutively.
            max_sequence_length: Length of sequence to track for pattern detection.
        """
        self._max_repeated_calls = max_repeated_calls
        self._max_sequence_length = max_sequence_length
        self._tool_history: list[str] = []
        self._loop_detected = False

        # before_tool/after_tool removed — dead code (agent_node never calls them).

    def is_loop_detected(self) -> bool:
        """Return whether a loop has been detected."""
        return self._loop_detected

    def get_loop_context(self) -> dict[str, Any]:
        """Return context about detected loops."""
        return {
            "loop_detected": self._loop_detected,
            "tool_history": list(self._tool_history),
            "max_repeated_calls": self._max_repeated_calls,
        }

    def reset(self) -> None:
        """Reset loop detection state."""
        self._tool_history.clear()
        self._loop_detected = False
