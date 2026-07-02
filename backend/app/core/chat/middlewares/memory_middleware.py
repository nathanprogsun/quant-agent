"""Memory middleware — evolution write-back hook (P4.4).

NO message injection happens here. Memory injection is the responsibility of
DynamicContextMiddleware (P4.2), which emits ``HumanMessage(id='{stable_id}__memory')``
anchored on the first user HumanMessage's id (D2). This middleware only
dispatches a flush trigger to the MemoryUpdateQueue (P4.5) from ``after_model``
when ``len(messages) >= max_messages``. Idempotency within a debounce window
is delegated to the queue (per-thread 30s debounce). deer-flow's
``memory_middleware.py`` uses ``after_agent``; quant-agent adapts to
``after_model`` (D1).
"""

from __future__ import annotations

import logging
from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import BaseMessage
from langgraph.runtime import Runtime

from app.core.chat.memory.queue import get_memory_update_queue
from app.core.chat.memory.summarization_hook import SummarizationEvent, memory_flush_hook

logger = logging.getLogger(__name__)


class MemoryMiddleware(AgentMiddleware):
    """Memory evolution write-back trigger (no injection).

    Args:
        max_messages: Message-count threshold that triggers a flush.
    """

    def __init__(self, max_messages: int = 50) -> None:
        self._max_messages = max_messages

    async def abefore_model(self, state: dict[str, Any], runtime: Runtime) -> dict[str, Any] | None:  # type: ignore[override]
        """No-op. Memory injection lives in DynamicContextMiddleware (P4.2)."""
        return None

    async def aafter_model(self, state: dict[str, Any], runtime: Runtime) -> dict[str, Any] | None:  # type: ignore[override]
        """Dispatch a flush trigger to the MemoryUpdateQueue when over threshold."""
        messages: list[BaseMessage] = list(state.get("messages", []))
        if len(messages) < self._max_messages:
            return None

        thread_id = str(runtime.context.thread_id if runtime.context else "") or "unknown"  # type: ignore[redundant-expr]
        user_id = runtime.context.user_id if runtime.context else None  # type: ignore[redundant-expr]

        event = SummarizationEvent(
            thread_id=thread_id,
            user_id=user_id,
            message_count=len(messages),
            messages=messages,
        )
        queue = get_memory_update_queue()
        if queue is None:
            logger.debug("Memory flush skipped: no MemoryUpdateQueue configured")
            return None
        # Idempotent within the per-thread debounce window (queue responsibility).
        memory_flush_hook(event, queue)
        return None
