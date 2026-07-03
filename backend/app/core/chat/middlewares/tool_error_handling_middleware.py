"""Middleware that converts tool exceptions into error ToolMessages.

When a tool raises an exception during execution, LangGraph's ToolNode would
otherwise propagate it up and abort the whole run. This middleware wraps
``wrap_tool_call`` / ``awrap_tool_call`` so that any exception (except
LangGraph control-flow signals, which must propagate) is converted into a
``ToolMessage(status="error")`` and returned to the model. The run stays
alive: the model sees the tool returned an error and can decide to retry,
fall back, or answer with the context it has.

This is the critical resilience layer for the jq_kb retrieval tools: a
transient embedding provider 503 / timeout / Chroma glitch no longer
terminates the conversation. Without it, a single ``search_jq_*`` failure
bubbles to ``run_agent`` and the run status becomes ERROR — the user sees
"处理请求时出错" and the entire conversation is lost.

Ported from deer-flow ``tool_error_handling_middleware.py`` without the
subagent-status stamping (quant-agent has no subagent contract).
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any, override

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import ToolMessage
from langgraph.errors import GraphBubbleUp
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.types import Command

logger = logging.getLogger(__name__)

# Sentinel id used when a tool_call has no ``id`` field. ToolNode pairs a
# ToolMessage back to its originating AIMessage tool_call by id, so we must
# always produce a non-empty id even when the request was malformed.
_MISSING_TOOL_CALL_ID = "missing_tool_call_id"


class ToolErrorHandlingMiddleware(AgentMiddleware[AgentState]):
    """Convert tool exceptions into error ToolMessages so the run continues.

    Hooks: ``wrap_tool_call`` (sync) and ``awrap_tool_call`` (async). Both
    try the handler; on any exception other than ``GraphBubbleUp`` they
    return a ``ToolMessage(status="error")`` whose content names the tool,
    the exception class, and a truncated detail message. ``GraphBubbleUp``
    (LangGraph interrupt / pause / resume signals) always re-raises.
    """

    def _build_error_message(self, request: ToolCallRequest, exc: Exception) -> ToolMessage:
        tool_name = str(request.tool_call.get("name") or "unknown_tool")
        tool_call_id = str(request.tool_call.get("id") or _MISSING_TOOL_CALL_ID)
        detail = str(exc).strip() or exc.__class__.__name__
        if len(detail) > 500:
            detail = detail[:497] + "..."

        content = (
            f"Error: Tool '{tool_name}' failed with {exc.__class__.__name__}: {detail}. "
            "Continue with available context, or choose an alternative tool."
        )
        return ToolMessage(
            content=content,
            tool_call_id=tool_call_id,
            name=tool_name,
            status="error",
        )

    @override
    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolMessage | Command[Any]],
    ) -> ToolMessage | Command[Any]:
        try:
            return handler(request)
        except GraphBubbleUp:
            # Preserve LangGraph control-flow signals (interrupt/pause/resume).
            raise
        except Exception as exc:
            logger.exception(
                "Tool execution failed (sync): name=%s id=%s",
                request.tool_call.get("name"),
                request.tool_call.get("id"),
            )
            return self._build_error_message(request, exc)

    @override
    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command[Any]]],
    ) -> ToolMessage | Command[Any]:
        try:
            return await handler(request)
        except GraphBubbleUp:
            # Preserve LangGraph control-flow signals (interrupt/pause/resume).
            raise
        except Exception as exc:
            logger.exception(
                "Tool execution failed (async): name=%s id=%s",
                request.tool_call.get("name"),
                request.tool_call.get("id"),
            )
            return self._build_error_message(request, exc)
