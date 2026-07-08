"""Middleware for intercepting clarification requests and presenting them to the user.

Ported from deer-flow clarification_middleware.py:159-200.
Pattern: the model calls the ``ask_clarification`` tool when it needs
more information. The middleware intercepts this call via
``awrap_tool_call``, formats a user-friendly message, and returns
``Command(goto=END)`` to interrupt execution and present the
question to the user.

Language-agnostic: the model writes the question in whatever language
the conversation uses. No regex, no LLM classifier in the middleware.

Note: ToolNode must invoke wrap_tool_call hooks for interception to
work. In quant-agent's current manual StateGraph, ToolNode does not
go through the middleware chain — this is a pending integration.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from hashlib import sha256
from typing import Any, override

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import ToolMessage
from langgraph.graph import END
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.types import Command

logger = logging.getLogger(__name__)


class ClarificationMiddleware(AgentMiddleware[AgentState]):
    """Intercepts ``ask_clarification`` tool calls and interrupts execution.

    When the model calls ``ask_clarification(question=..., options=[...])``,
    this middleware:
    1. Intercepts the tool call before execution (via awrap_tool_call)
    2. Extracts the question, type, context, and options
    3. Formats a user-friendly message with icons
    4. Returns Command(goto=END) to interrupt execution and present the
       question to the user
    """

    def _stable_message_id(self, tool_call_id: str, formatted_message: str) -> str:
        if tool_call_id:
            return f"clarification:{tool_call_id}"
        digest = sha256(formatted_message.encode("utf-8")).hexdigest()[:16]
        return f"clarification:{digest}"

    @staticmethod
    def _is_chinese(text: str) -> bool:
        return any("一" <= char <= "鿿" for char in text)

    def _format_clarification_message(self, args: dict[str, Any]) -> str:
        question = args.get("question", "")
        clarification_type = args.get("clarification_type", "missing_info")
        context = args.get("context")
        options = args.get("options", [])

        if isinstance(options, str):
            try:
                options = json.loads(options)
            except (json.JSONDecodeError, TypeError):
                options = [options]
        if options is None:
            options = []
        elif not isinstance(options, list):
            options = [options]

        type_icons = {
            "missing_info": "❇",  # ❓
            "ambiguous_requirement": "\U0001f914",  # 🤔
            "approach_choice": "\U0001f500",  # 🔀
            "risk_confirmation": "⚠️",  # ⚠️
            "suggestion": "\U0001f4a1",  # 💡
        }
        icon = type_icons.get(clarification_type, "❇")

        message_parts: list[str] = []
        if context:
            message_parts.append(f"{icon} {context}")
            message_parts.append(f"\n{question}")
        else:
            message_parts.append(f"{icon} {question}")

        if options:
            message_parts.append("")
            for i, option in enumerate(options, 1):
                message_parts.append(f"  {i}. {option}")

        return "\n".join(message_parts)

    def _handle_clarification(self, request: ToolCallRequest) -> Command[Any]:
        args = request.tool_call.get("args", {})
        question = args.get("question", "")
        logger.info("Intercepted clarification request: %s", question)

        formatted_message = self._format_clarification_message(args)
        tool_call_id = request.tool_call.get("id", "")

        tool_message = ToolMessage(
            id=self._stable_message_id(tool_call_id, formatted_message),  # type: ignore[arg-type]
            content=formatted_message,
            tool_call_id=tool_call_id,
            name="ask_clarification",
        )

        return Command(update={"messages": [tool_message]}, goto=END)

    # -- sync / async wrap_tool_call (the key hook) --

    @override
    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolMessage | Command[Any]],
    ) -> ToolMessage | Command[Any]:
        if request.tool_call.get("name") != "ask_clarification":
            return handler(request)
        return self._handle_clarification(request)

    @override
    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command[Any]]],
    ) -> ToolMessage | Command[Any]:
        if request.tool_call.get("name") != "ask_clarification":
            return await handler(request)
        return self._handle_clarification(request)
