"""Intent recognition middleware — classifies user intent from AI output.

P3: Extracts the user's intent category from the AIMessage content and writes
it to ``ThreadState.intent`` for downstream routing and analytics.
"""

from __future__ import annotations

import re
from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import AIMessage
from langgraph.runtime import Runtime

# Intent taxonomy — matches the categories defined in the system prompt
INTENT_TYPES = "chat|strategy_build|backtest|market_query|code_review|file_analysis|unknown"

_INTENT_RE = re.compile(
    r"(?:意图|intent)[：:]\s*"
    r"(chat|strategy_build|backtest|market_query|code_review|file_analysis|unknown)",
    re.IGNORECASE,
)


class IntentMiddleware(AgentMiddleware):
    """Extracts user intent from the AIMessage and persists to ThreadState.intent.

    Runs in ``aafter_model`` so it sees the final AIMessage. Reads the
    ``<intent>`` tag or ``意图:`` marker from the response content. Only
    updates when intent is found and differs from the current value.
    """

    async def aafter_model(  # type: ignore[override]
        self, state: dict[str, Any], runtime: Runtime
    ) -> dict[str, Any] | None:
        messages = state.get("messages", [])
        if not messages:
            return None

        last = messages[-1]
        if not isinstance(last, AIMessage) or last.tool_calls:
            return None

        content = _message_text(last)
        if not content:
            return None

        intent = _extract_intent(content)
        if intent is None:
            return None

        # Only update if intent changed — preserve previous_intent for
        # ToolFilterMiddleware to read on the next turn.
        current = state.get("intent")
        if intent == current:
            return None

        return {
            "previous_intent": current,
            "intent": intent,
        }


def _extract_intent(content: str) -> str | None:
    """Extract intent from AIMessage content.

    Looks for:
    1. ``<intent>strategy_build</intent>`` XML-style tag
    2. ``意图: strategy_build`` inline marker
    """
    # Try XML-style tag first
    tag_match = re.search(r"<intent>\s*(\w+)\s*</intent>", content, re.IGNORECASE)
    if tag_match:
        raw = tag_match.group(1).lower()
        if raw in _VALID_INTENTS:
            return raw

    # Try inline marker
    inline_match = _INTENT_RE.search(content)
    if inline_match:
        return inline_match.group(1).lower()

    return None


_VALID_INTENTS = frozenset(
    {
        "chat",
        "strategy_build",
        "backtest",
        "market_query",
        "code_review",
        "file_analysis",
        "unknown",
    }
)


def _message_text(message: AIMessage) -> str:
    """Extract text content from an AIMessage."""
    content = message.content
    if isinstance(content, str):
        return content.strip()
    parts: list[str] = []
    for block in content:
        if isinstance(block, str):
            parts.append(block)
        elif isinstance(block, dict):
            text = block.get("text")
            if isinstance(text, str):
                parts.append(text)
    return " ".join(parts).strip()
