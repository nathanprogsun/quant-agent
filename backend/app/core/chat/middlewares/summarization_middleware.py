"""Summarization middleware (P4.5).

Replaces the flag-only stub with a hook dispatch: when a conversation crosses
``max_messages``, ``after_model`` builds a ``SummarizationEvent`` and forwards
it to the registered flush hook (bridging to the MemoryUpdateQueue via
``memory_flush_hook``). deer-flow's summarization is wired to ``after_agent``;
quant-agent adapts to ``after_model`` (D1).
"""

from __future__ import annotations

import logging
from typing import Any, NotRequired, override

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import BaseMessage
from langgraph.runtime import Runtime

from app.core.chat.memory.summarization_hook import (
    SummarizationEvent,
    dispatch_summarization_hooks,
    get_summarization_flush_hook,
)

logger = logging.getLogger(__name__)


class SummarizationMiddlewareState(AgentState):
    """State written by :class:`SummarizationMiddleware`."""

    should_summarize: NotRequired[bool]
    message_count: NotRequired[int]
    summarization_pending: NotRequired[bool]
    max_messages: NotRequired[int]


class SummarizationMiddleware(AgentMiddleware[SummarizationMiddlewareState]):
    """Dispatches a SummarizationEvent when a conversation gets too long."""

    def __init__(self, max_messages: int = 50, enabled: bool = True) -> None:
        self._max_messages = max_messages
        self._enabled = enabled
        self._should_summarize = False
        self._pending_message_count = 0

    @override
    async def abefore_model(
        self,
        state: SummarizationMiddlewareState,
        runtime: Runtime,
    ) -> dict[str, Any] | None:
        if not self._enabled:
            return None
        messages: list[BaseMessage] = list(state.get("messages", []))
        count = len(messages)
        if count >= self._max_messages:
            self._should_summarize = True
            self._pending_message_count = count
            return {"should_summarize": True, "message_count": count}
        return None

    @override
    async def aafter_model(
        self,
        state: SummarizationMiddlewareState,
        runtime: Runtime,
    ) -> dict[str, Any] | None:
        if not self._should_summarize:
            return None
        self._should_summarize = False
        count = self._pending_message_count
        self._pending_message_count = 0

        messages: list[BaseMessage] = list(state.get("messages", []))
        ctx = runtime.context
        thread_id = str(ctx.thread_id) if ctx else "unknown"  # type: ignore[redundant-expr]
        user_id = ctx.user_id if ctx else None  # type: ignore[redundant-expr]

        # ``messages`` is held as a tuple so the frozen dataclass is
        # actually immutable — prevents subscribers from aliasing the list.
        event = SummarizationEvent(
            thread_id=thread_id,
            user_id=user_id,
            message_count=count,
            messages=tuple(messages),
        )
        hook = get_summarization_flush_hook()
        if hook is not None:
            try:
                hook(event)
            except Exception:
                logger.exception("Summarization flush hook failed")
        dispatch_summarization_hooks(event)
        return {"summarization_pending": True, "max_messages": self._max_messages}

    def is_enabled(self) -> bool:
        return self._enabled

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled

    def get_max_messages(self) -> int:
        return self._max_messages
