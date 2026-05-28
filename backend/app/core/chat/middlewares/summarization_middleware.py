"""Summarization middleware."""

from __future__ import annotations

from typing import Any

from app.core.chat.middlewares.base import AgentMiddleware


class SummarizationMiddleware(AgentMiddleware):
    """Handles conversation summarization when it gets too long.

    Can trigger summarization based on message count or token threshold.
    """

    def __init__(self, max_messages: int = 50, enabled: bool = True) -> None:
        """Initialize summarization middleware.

        Args:
            max_messages: Maximum messages before summarization is suggested.
            enabled: Whether summarization is enabled.
        """
        self._max_messages = max_messages
        self._enabled = enabled
        self._should_summarize = False

    async def before_model(self, state: dict[str, Any], config: dict[str, Any]) -> dict[str, Any] | None:
        """Check if summarization is needed before model call."""
        if not self._enabled:
            return None

        messages = state.get("messages", [])
        message_count = len(messages)

        if message_count >= self._max_messages:
            self._should_summarize = True
            return {
                "should_summarize": True,
                "message_count": message_count,
            }

        return None

    async def after_model(self, state: dict[str, Any], config: dict[str, Any]) -> dict[str, Any] | None:
        """After model - add summarization context if needed."""
        if self._should_summarize:
            self._should_summarize = False  # Reset after handling
            return {
                "summarization_pending": True,
                "max_messages": self._max_messages,
            }
        return None

    def is_enabled(self) -> bool:
        """Return whether summarization is enabled."""
        return self._enabled

    def set_enabled(self, enabled: bool) -> None:
        """Enable or disable summarization."""
        self._enabled = enabled

    def get_max_messages(self) -> int:
        """Return the maximum message count threshold."""
        return self._max_messages
