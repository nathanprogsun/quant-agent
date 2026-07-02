"""Middleware to filter deferred tool schemas from model binding.

When ``tool_search`` is enabled, MCP tools still reach ``ToolNode`` for
execution routing, but their schemas must NOT be sent to the LLM via
``bind_tools`` until the model has discovered them via ``tool_search``.
This middleware removes the still-deferred tool names from the bound
model's request, and blocks tool calls to a tool that has not been
promoted yet.

The deferred name set and the catalog hash are closed over at construction
time (no ContextVar). Promotion state is read from graph state via
``state["promoted"]``, scoped by catalog hash so a stale persisted
promotion cannot expose a renamed or drifted tool.

Adapts to quant-agent's custom ``AgentMiddleware`` ABC (deer-flow uses
``langchain.agents.middleware.AgentMiddleware`` with ``ModelRequest`` /
``ToolCallRequest``; here we read ``ModelCallRequest`` shapes directly).
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import ToolMessage

from app.core.chat.agent.model_call import ModelCallRequest

logger = logging.getLogger(__name__)


def _state_for(request: ModelCallRequest | Any) -> dict[str, Any]:
    """Best-effort extraction of ``state`` from a request-like object."""
    if hasattr(request, "state"):
        return request.state or {}
    state = getattr(request, "state", None)
    return state if isinstance(state, dict) else {}


def _tools_for(request: ModelCallRequest | Any) -> list[Any]:
    """Best-effort extraction of ``tools`` from a request-like object."""
    if isinstance(request, ModelCallRequest):
        return list(request.tools or [])
    return list(getattr(request, "tools", None) or [])


def _tool_name(t: Any) -> str | None:
    return getattr(t, "name", None) or getattr(t, "__name__", None)


def _tools_override(request: ModelCallRequest, new_tools: list[Any]) -> ModelCallRequest:
    """Return a new ``ModelCallRequest`` with ``tools`` replaced."""
    return ModelCallRequest(messages=list(request.messages), tools=new_tools)


class DeferredToolFilterMiddleware(AgentMiddleware):
    """Hide deferred tool schemas from the bound model until promoted."""

    def __init__(self, deferred_names: frozenset[str], catalog_hash: str | None) -> None:
        super().__init__()
        self._deferred = deferred_names
        self._catalog_hash = catalog_hash

    # ── internal helpers ────────────────────────────────────────

    def _promoted(self, state: dict[str, Any]) -> set[str]:
        promoted = state.get("promoted")
        if not promoted:
            return set()
        if promoted.get("catalog_hash") != self._catalog_hash:
            # Stale promotion (catalog renamed/refreshed); ignore it so a
            # renamed tool does not silently reappear.
            return set()
        return set(promoted.get("names") or [])

    def _hidden(self, state: dict[str, Any]) -> set[str]:
        return set(self._deferred) - self._promoted(state)

    def _filter_tools(self, request: ModelCallRequest) -> ModelCallRequest:
        if not self._deferred:
            return request
        hide = self._hidden(_state_for(request))
        if not hide:
            return request
        tools = _tools_for(request)
        active = [t for t in tools if _tool_name(t) not in hide]
        if len(active) < len(tools):
            logger.debug(
                "Filtered %d deferred tool schema(s) from model binding",
                len(tools) - len(active),
            )
        return _tools_override(request, active)

    def _blocked_tool_message(self, request: Any) -> ToolMessage | None:
        if not self._deferred:
            return None
        # ``request`` is a ToolCall-shaped object whose ``tool_call`` is
        # either a dict (LangGraph ToolCallRequest) or has .name/.id attrs.
        tool_call = getattr(request, "tool_call", None) or {}
        if isinstance(tool_call, dict):
            name = str(tool_call.get("name") or "")
            tc_id = str(tool_call.get("id") or "missing_tool_call_id")
        else:
            name = str(getattr(tool_call, "name", "") or "")
            tc_id = str(getattr(tool_call, "id", None) or "missing_tool_call_id")
        if not name or name not in self._hidden(_state_for(request)):
            return None
        return ToolMessage(
            content=(
                f"Error: Tool '{name}' is deferred and has not been promoted yet. "
                f"Call tool_search first to expose and promote this tool's schema, "
                f"then retry."
            ),
            tool_call_id=tc_id,
            name=name,
            status="error",
        )

    # ── wrap hooks (sync + async) ───────────────────────────────

    async def awrap_model_call(  # type: ignore[override]
        self,
        request: ModelCallRequest,
        handler: Callable[[ModelCallRequest], Awaitable[Any]],
    ) -> Any:
        return await handler(self._filter_tools(request))

    def wrap_model_call(  # type: ignore[override]
        self,
        request: ModelCallRequest,
        handler: Callable[[ModelCallRequest], Any],
    ) -> Any:
        return handler(self._filter_tools(request))

    async def awrap_tool_call(
        self,
        request: Any,
        handler: Callable[[Any], Awaitable[Any]],
    ) -> Any:
        blocked = self._blocked_tool_message(request)
        if blocked is not None:
            return blocked
        return await handler(request)

    def wrap_tool_call(
        self,
        request: Any,
        handler: Callable[[Any], Any],
    ) -> Any:
        blocked = self._blocked_tool_message(request)
        if blocked is not None:
            return blocked
        return handler(request)


__all__ = ["DeferredToolFilterMiddleware"]
