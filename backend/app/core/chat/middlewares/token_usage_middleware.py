"""Token usage tracking middleware."""

from __future__ import annotations

from typing import Any

from app.core.chat.middlewares.base import AgentMiddleware


class TokenUsageMiddleware(AgentMiddleware):
    """Tracks token usage across the conversation.

    Accumulates token counts from model responses.
    """

    def __init__(self) -> None:
        self._total_tokens = 0
        self._prompt_tokens = 0
        self._completion_tokens = 0
        self._turn_count = 0

    async def after_model(self, state: dict[str, Any], config: dict[str, Any]) -> dict[str, Any] | None:
        """Extract and accumulate token usage from model response."""
        messages = state.get("messages", [])
        if not messages:
            return None

        last_message = messages[-1]
        # Check for token usage metadata (varies by model provider)
        usage = getattr(last_message, "usage", None)
        if usage:
            self._prompt_tokens += getattr(usage, "prompt_tokens", 0)
            self._completion_tokens += getattr(usage, "completion_tokens", 0)
            self._total_tokens += getattr(usage, "total_tokens", 0)
            self._turn_count += 1

        return {
            "token_usage": {
                "prompt_tokens": self._prompt_tokens,
                "completion_tokens": self._completion_tokens,
                "total_tokens": self._total_tokens,
                "turn_count": self._turn_count,
            }
        }

    def get_usage_stats(self) -> dict[str, int]:
        """Return accumulated token usage statistics."""
        return {
            "prompt_tokens": self._prompt_tokens,
            "completion_tokens": self._completion_tokens,
            "total_tokens": self._total_tokens,
            "turn_count": self._turn_count,
        }

    def reset(self) -> None:
        """Reset token counters."""
        self._total_tokens = 0
        self._prompt_tokens = 0
        self._completion_tokens = 0
        self._turn_count = 0
