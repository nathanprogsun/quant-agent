"""Intent-based tool filtering middleware — reduces token overhead.

Dynamically binds only intent-relevant tools to the LLM, reducing the
number of tool schemas sent per request. On the first turn (intent is
``None``), all tools are sent. On subsequent turns, only tools mapped to
the classified intent are included.

Intent → tool mapping:
- chat: ask_clarification, read_file
- strategy_build: lint_code_tool, validate_strategy_parameters, read_file,
                   ask_clarification, search_jq_api, search_jq_dict,
                   search_jq_strategy, tool_search
- backtest: lint_code_tool, validate_strategy_parameters, read_file,
            search_jq_api, search_jq_dict, search_jq_strategy, tool_search
- market_query: search_jq_api, search_jq_dict, search_jq_strategy, tool_search
- code_review: lint_code_tool, validate_strategy_parameters, read_file
- file_analysis: read_file, search_jq_api, search_jq_dict, search_jq_strategy
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from langchain.agents.middleware import AgentMiddleware, ModelRequest

logger = logging.getLogger(__name__)

# Intent → set of tool names that are relevant.
# MCP tools and tool_search are included when relevant (tool_search is
# always available since it's the mechanism to discover MCP tools).
INTENT_TOOL_MAP: dict[str, frozenset[str]] = {
    "chat": frozenset(
        {
            "ask_clarification",
            "read_file",
        }
    ),
    "strategy_build": frozenset(
        {
            "lint_code_tool",
            "validate_strategy_parameters",
            "read_file",
            "ask_clarification",
            "search_jq_api",
            "search_jq_dict",
            "search_jq_strategy",
            "tool_search",
        }
    ),
    "backtest": frozenset(
        {
            "lint_code_tool",
            "validate_strategy_parameters",
            "read_file",
            "search_jq_api",
            "search_jq_dict",
            "search_jq_strategy",
            "tool_search",
        }
    ),
    "market_query": frozenset(
        {
            "search_jq_api",
            "search_jq_dict",
            "search_jq_strategy",
            "tool_search",
        }
    ),
    "code_review": frozenset(
        {
            "lint_code_tool",
            "validate_strategy_parameters",
            "read_file",
        }
    ),
    "file_analysis": frozenset(
        {
            "read_file",
            "search_jq_api",
            "search_jq_dict",
            "search_jq_strategy",
        }
    ),
}


def _state_for(request: ModelRequest | Any) -> dict[str, Any]:
    """Best-effort extraction of ``state`` from a request-like object."""
    if hasattr(request, "state"):
        return request.state or {}  # type: ignore[return-value]
    state = getattr(request, "state", None)
    return state if isinstance(state, dict) else {}


def _tools_for(request: ModelRequest | Any) -> list[Any]:
    """Best-effort extraction of ``tools`` from a request-like object."""
    return list(getattr(request, "tools", None) or [])


def _tool_name(t: Any) -> str | None:
    return getattr(t, "name", None) or getattr(t, "__name__", None)


class ToolFilterMiddleware(AgentMiddleware):
    """Filter tool schemas based on classified intent.

    Runs in ``awrap_model_call`` to intercept the model request and remove
    tools that are not relevant to the current intent. This reduces token
    overhead by sending fewer tool schemas per LLM call.

    On the first turn (intent is ``None``), all tools are sent. On
    subsequent turns, only tools mapped to the classified intent are
    included. MCP tools are always included when relevant (they're
    discovered via ``tool_search``).
    """

    def _filter_tools(self, request: ModelRequest) -> ModelRequest:
        state = _state_for(request)
        intent = state.get("intent")

        # No intent yet (first turn) — send all tools
        if not intent or intent not in INTENT_TOOL_MAP:
            return request

        allowed = INTENT_TOOL_MAP[intent]
        tools = _tools_for(request)
        active = [t for t in tools if _tool_name(t) in allowed]

        if len(active) < len(tools):
            logger.debug(
                "Filtered tools for intent=%s: %d → %d schemas",
                intent,
                len(tools),
                len(active),
            )

        return request.override(tools=active)

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[Any]],
    ) -> Any:
        return await handler(self._filter_tools(request))

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Any],
    ) -> Any:
        return handler(self._filter_tools(request))


__all__ = ["INTENT_TOOL_MAP", "ToolFilterMiddleware"]
