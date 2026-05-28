"""Dynamic context injection middleware."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.core.chat.middlewares.base import AgentMiddleware


class DynamicContextMiddleware(AgentMiddleware):
    """Injects current datetime and timezone before model call.

    Adds context about current time to help the model make time-aware decisions.
    """

    async def before_model(self, state: dict[str, Any], config: dict[str, Any]) -> dict[str, Any] | None:
        """Inject current datetime context into messages."""
        messages = list(state.get("messages", []))
        if not messages:
            return None

        now = datetime.now(timezone.utc)
        context = (
            f"\n\n[System Context] Current UTC datetime: {now.strftime('%Y-%m-%d %H:%M:%S')} | "
            f"Timezone: UTC | This context is automatically injected for time-aware responses."
        )

        # Inject after system message if present
        if messages and hasattr(messages[0], "content") and "[System Context]" not in str(messages[0].content):
            system_content = messages[0].content if isinstance(messages[0].content, str) else str(messages[0].content)
            messages[0] = messages[0].__class__(content=system_content + context)
        else:
            # Prepend context message
            from langchain_core.messages import HumanMessage
            messages.insert(1, HumanMessage(content=context))

        return {"messages": messages}
