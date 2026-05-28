"""Clarification detection middleware."""

from __future__ import annotations

import re
from typing import Any

from app.core.chat.middlewares.base import AgentMiddleware


class ClarificationMiddleware(AgentMiddleware):
    """Detects when the AI is asking for clarification.

    Monitors model responses to identify clarification patterns and
    can flag or handle them appropriately.
    """

    # Patterns that indicate clarification requests
    CLARIFICATION_PATTERNS = [
        r"could you (please\s)?(clarify|explain|elaborate|provide more)",
        r"can you (please\s)?(clarify|explain|elaborate|provide more)",
        r"would you (please\s)?(clarify|explain|elaborate)",
        r"i need (more|additional|further)\s*(information|details|clarification)",
        r"could you give me (more|additional)\s*(information|details)",
        r"i'm not (quite|sure|clear)\s*(sure|clear) what you mean",
        r"could you (rephrase|restate|clarify)",
        r"what do you mean by",
        r"i'm (a little|slightly)\s*confused",
        r"could you (go|be) more (specific|precise)",
        r"please (clarify|explain) (what|how|when|where|why)",
        r"just to (clarify|confirm|make sure)",
        r"so (just to be clear|to clarify)",
    ]

    def __init__(self) -> None:
        self._patterns = [re.compile(p, re.IGNORECASE) for p in self.CLARIFICATION_PATTERNS]

    def _is_clarification_request(self, text: str) -> bool:
        """Check if text contains clarification request patterns."""
        for pattern in self._patterns:
            if pattern.search(text):
                return True
        return False

    async def after_model(self, state: dict[str, Any], config: dict[str, Any]) -> dict[str, Any] | None:
        """Detect clarification requests in model response."""
        messages = state.get("messages", [])
        if not messages:
            return None

        last_message = messages[-1]
        if not hasattr(last_message, "content"):
            return None

        content = last_message.content
        if isinstance(content, list):
            # Handle multimodal content
            text = " ".join(
                item.get("text", "") for item in content if isinstance(item, dict) and item.get("type") == "text"
            )
        else:
            text = str(content)

        if self._is_clarification_request(text):
            # Add metadata to track clarification requests
            return {
                "requires_clarification": True,
                "last_message_was_clarification": True,
            }

        return {"last_message_was_clarification": False}
