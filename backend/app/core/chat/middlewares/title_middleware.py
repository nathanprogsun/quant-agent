"""Title middleware - generates conversation titles."""

from __future__ import annotations

from typing import Any

from app.core.chat.middlewares.base import AgentMiddleware


class TitleMiddleware(AgentMiddleware):
    """Generates a title for the conversation.

    Analyzes initial messages to generate a concise title.
    """

    def __init__(self) -> None:
        self._title_generated = False
        self._title: str | None = None

    async def after_model(self, state: dict[str, Any], config: dict[str, Any]) -> dict[str, Any] | None:
        """Generate title from conversation if not already generated."""
        if self._title_generated or state.get("title"):
            return None

        messages = state.get("messages", [])
        if not messages:
            return None

        # Generate title from first user message
        for msg in messages:
            if hasattr(msg, "type") and msg.type == "human":
                content = msg.content
                if isinstance(content, str):
                    # Simple title generation: take first N chars
                    title = content[:50].strip()
                    if len(content) > 50:
                        title += "..."
                    self._title = title
                    self._title_generated = True
                    return {"title": title}
                break

        return None

    def get_title(self) -> str | None:
        """Return generated title."""
        return self._title
