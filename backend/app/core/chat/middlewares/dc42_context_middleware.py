"""Inject DC42 retrieval context before model calls."""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.core.chat.middlewares.base import AgentMiddleware
from app.core.dc42.retriever import DC42Retriever, create_default_retriever
from app.core.generation.context_builder import DEFAULT_TOP_K, build_dc42_context, load_dc42_ranges

logger = logging.getLogger(__name__)

_DC42_CONTEXT_MARKER = "[DC42 Knowledge]"


class DC42ContextMiddleware(AgentMiddleware):
    """Retrieve DC42 chunks for the latest user message and append to system prompt."""

    def __init__(
        self,
        retriever: DC42Retriever | None = None,
        *,
        top_k: int = DEFAULT_TOP_K,
    ) -> None:
        self._retriever = retriever
        self._top_k = top_k
        self._retriever_initialized = retriever is not None

    def _get_retriever(self) -> DC42Retriever | None:
        if self._retriever is not None:
            return self._retriever
        if self._retriever_initialized:
            return None
        self._retriever_initialized = True
        try:
            self._retriever = create_default_retriever()
        except Exception:
            logger.exception("Failed to initialize default DC42 retriever")
            self._retriever = None
        return self._retriever

    async def before_model(
        self,
        state: dict[str, Any],
        config: dict[str, Any],
    ) -> dict[str, Any] | None:
        retriever = self._get_retriever()
        if retriever is None:
            return None

        user_query = _latest_human_content(state.get("messages", []))
        if not user_query:
            return None

        dc42_context = await build_dc42_context(
            user_query,
            retriever,
            top_k=self._top_k,
        )
        if not dc42_context:
            return None

        messages = list(state.get("messages", []))
        if not messages:
            return None

        block = f"\n\n{_DC42_CONTEXT_MARKER}\n{dc42_context}"
        if isinstance(messages[0], SystemMessage):
            content = messages[0].content
            text = content if isinstance(content, str) else str(content)
            if _DC42_CONTEXT_MARKER in text:
                return None
            messages[0] = SystemMessage(content=text + block)
        else:
            messages.insert(0, SystemMessage(content=block.strip()))

        return {
            "messages": messages,
            "dc42_ranges": load_dc42_ranges(),
        }


def _latest_human_content(messages: list[Any]) -> str:
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            content = message.content
            if isinstance(content, str) and content.strip():
                return content.strip()
    for message in reversed(messages):
        if getattr(message, "type", None) == "human":
            content = message.content
            if isinstance(content, str) and content.strip():
                return content.strip()
    return ""
