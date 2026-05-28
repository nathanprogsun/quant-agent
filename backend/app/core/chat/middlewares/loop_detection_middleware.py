"""Loop detection middleware."""

from __future__ import annotations

from collections import Counter
from typing import Any

from app.core.chat.middlewares.base import AgentMiddleware


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

    async def before_tool(self, tool_name: str, tool_input: dict[str, Any], config: dict[str, Any]) -> dict[str, Any] | None:
        """Check for loop patterns before tool execution."""
        self._tool_history.append(tool_name)
        if len(self._tool_history) > self._max_sequence_length:
            self._tool_history.pop(0)

        # Check for repeated tool calls
        if len(self._tool_history) >= self._max_repeated_calls:
            recent = self._tool_history[-self._max_repeated_calls:]
            if all(t == tool_name for t in recent):
                self._loop_detected = True
                # Allow execution but flag it

        return None

    async def after_tool(
        self, tool_name: str, tool_input: dict[str, Any], result: Any, config: dict[str, Any]
    ) -> Any | None:
        """After tool call - analyze result for additional loop signals."""
        # If tool returned empty/error consistently, could indicate a loop
        if result is None or (isinstance(result, dict) and not result):
            self._loop_detected = True
        return None

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
