"""System message coalescing middleware.

Merges multiple ``SystemMessage`` instances into a single leading
``SystemMessage`` so strict backends (vLLM, SGLang, Qwen, Anthropic) that
reject non-leading system prompts accept the request. Persistent state is
not modified — coalescing is a request-time transformation only.

Mirrors legacy ``system_message_coalescing_middleware.py`` adapted to
quant-agent's ``ModelRequest`` carrier.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from langchain.agents.middleware import AgentMiddleware, ModelRequest
from langchain_core.messages import BaseMessage, SystemMessage

_DEFAULT_SEPARATOR = "\n\n"


class SystemMessageCoalescingMiddleware(AgentMiddleware):
    """Merge multiple SystemMessages into one at the front of the list.

    Args:
        enabled: Master switch.
        separator: String placed between merged contents.
    """

    def __init__(self, *, enabled: bool = True, separator: str = _DEFAULT_SEPARATOR) -> None:
        super().__init__()
        self._enabled = enabled
        self._separator = separator

    def _coalesce(self, messages: list[BaseMessage]) -> list[BaseMessage]:
        sys_msgs = [m for m in messages if isinstance(m, SystemMessage)]
        non_sys = [m for m in messages if not isinstance(m, SystemMessage)]
        if len(sys_msgs) <= 1:
            return messages
        merged_content = self._separator.join(
            m.content if isinstance(m.content, str) else str(m.content) for m in sys_msgs
        )
        # Preserve id of the FIRST SystemMessage so add_messages reducer
        # can replace in place when persistence happens to record this.
        merged = SystemMessage(
            content=merged_content,
            id=sys_msgs[0].id,
            additional_kwargs=sys_msgs[0].additional_kwargs,
        )
        return [merged, *non_sys]

    def _transform(self, request: ModelRequest) -> ModelRequest:
        if not self._enabled:
            return request
        new_messages = self._coalesce(list(request.messages))
        if new_messages is request.messages or len(new_messages) == len(request.messages):
            changed = False
            for old, new in zip(request.messages, new_messages):
                if old is not new:
                    changed = True
                    break
            if not changed:
                return request
        return request.override(messages=new_messages)  # type: ignore[arg-type]

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[Any]],
    ) -> Any:
        return await handler(self._transform(request))

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Any],
    ) -> Any:
        return handler(self._transform(request))
