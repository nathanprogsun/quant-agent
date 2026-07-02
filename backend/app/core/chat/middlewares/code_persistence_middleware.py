"""Code persistence middleware — extracts Python code blocks from AI replies.

P0: Automatically captures strategy code from AIMessage content and writes
it to ``ThreadState.code`` so multi-turn conversations can reference
previously generated code.
"""

from __future__ import annotations

import re
from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import AIMessage
from langgraph.runtime import Runtime

_CODE_BLOCK_RE = re.compile(r"```python\s*\n([\s\S]*?)```", re.IGNORECASE)


def _extract_python_code(content: str) -> str | None:
    """Extract the largest Python code block from markdown content."""
    matches = _CODE_BLOCK_RE.findall(content)
    if not matches:
        return None
    # Return the longest code block (most likely the main strategy)
    return max(matches, key=len).strip() or None


class CodePersistenceMiddleware(AgentMiddleware):
    """Extracts Python code from AI responses and persists to ThreadState.code.

    Runs in ``aafter_model`` so it sees the final AIMessage after tool calls.
    Only updates when a new, non-empty code block is found that differs from
    the current ``state["code"]``.
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

        code = _extract_python_code(content)
        if code is None:
            return None

        # Only update if code actually changed
        if code == state.get("code"):
            return None

        return {"code": code}


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
