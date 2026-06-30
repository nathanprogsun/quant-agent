"""Middleware to fix dangling tool calls in message history.

A dangling tool call occurs when an AIMessage declares ``tool_calls``
but the corresponding ``ToolMessage`` results are missing — most
commonly because of user interruption, request cancellation, or a
subagent crash. Without a synthetic placeholder, OpenAI-compatible
reasoning-model endpoints return 400 on the next ``ainvoke``.

This middleware inspects ``request.messages`` *before* the LLM call
(via ``awrap_model_call`` / ``wrap_model_call``) and re-orders causal
ToolMessages adjacent to their dispatch AIMessage. Dangling calls are
synthesised as ``ToolMessage(status='error', ...)``.

Ports ``deerflow.agents.middlewares.dangling_tool_call_middleware``.
Adapts to quant-agent's custom ``AgentMiddleware`` ABC: instead of
``request.override(messages=...)`` (langchain-style), we mutate
``request.messages`` in place — the agent_node reads
``request.messages`` back out so the patched list persists in graph state.
"""
from __future__ import annotations

import json
import logging
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable, Sequence
from typing import Any, override

from langchain_core.messages import AIMessage, BaseMessage, ToolMessage

from app.core.chat.agent.model_call import ModelCallRequest
from app.core.chat.middlewares.base import AgentMiddleware

logger = logging.getLogger(__name__)

# Workaround for issue #2894: malformed write_file calls can carry huge
# Markdown payloads in invalid tool-call args. Keep recovery error details
# short so the synthetic ToolMessage does not echo large or malformed
# content back to the model.
_MAX_RECOVERY_ERROR_DETAIL_LEN = 500

_WRITE_FILE_PRESCRIPTION = (
    "[write_file failed before execution: the tool-call arguments were not valid JSON, "
    "so no file was written. This often happens when the model tries to write a very "
    "large Markdown file in a single tool call, especially when `content` contains "
    "unescaped quotes, inline JSON, backslashes, or code fences. Do not retry the same "
    "large `write_file` payload for this artifact; provide the report/content directly "
    "as normal assistant text in your next response. If a file write is still needed "
    "later, split the file into smaller sections instead of one large payload.{details}]"
)

_GENERIC_RECOVERY_NO_DETAIL = (
    "[Tool call could not be executed because its arguments were invalid.]"
)

_GENERIC_RECOVERY_WITH_DETAIL = (
    "[Tool call could not be executed because its arguments were invalid: {error_text}]"
)

_INTERRUPTED_FALLBACK = "[Tool call was interrupted and did not return a result.]"


def _cap_error_detail(error: object) -> str:
    """Truncate the error text to ``_MAX_RECOVERY_ERROR_DETAIL_LEN``."""
    if isinstance(error, str) and error:
        return error[:_MAX_RECOVERY_ERROR_DETAIL_LEN]
    return ""


class DanglingToolCallMiddleware(AgentMiddleware):
    """Insert placeholder ToolMessages for dangling tool calls before model invocation.

    Scans the message history for AIMessages whose ``tool_calls`` lack
    matching ``ToolMessages``, and injects synthetic error responses
    immediately after the offending AIMessage so the LLM receives a
    well-formed conversation.
    """

    # ── helpers ─────────────────────────────────────────────────

    @staticmethod
    def _message_tool_calls(msg: BaseMessage) -> list[dict[str, Any]]:
        """Normalize tool-call records from structured and raw-provider fields.

        LangChain stores malformed provider function calls in
        ``invalid_tool_calls``. They do not execute, but strict
        OpenAI-compatible validators may still serialize enough of
        the call id/name back into the next request that they expect a
        matching ToolMessage. Treat them as dangling calls so the
        next model request stays well-formed and the model sees a
        recoverable tool error instead of another provider 400.
        """
        normalized: list[dict[str, Any]] = []

        raw_structured = getattr(msg, "tool_calls", None) or []
        if raw_structured:
            for entry in raw_structured:
                if not isinstance(entry, dict):
                    continue
                normalized.append(entry)

        raw_extra = (getattr(msg, "additional_kwargs", None) or {}).get("tool_calls") or []
        if not raw_structured and raw_extra:
            for raw_tc in raw_extra:
                if not isinstance(raw_tc, dict):
                    continue
                function = raw_tc.get("function")
                name = raw_tc.get("name")
                if not name and isinstance(function, dict):
                    name = function.get("name")

                args = raw_tc.get("args", {})
                if not args and isinstance(function, dict):
                    raw_args = function.get("arguments")
                    if isinstance(raw_args, str):
                        try:
                            parsed_args = json.loads(raw_args)
                        except (TypeError, ValueError, json.JSONDecodeError):
                            parsed_args = {}
                        args = parsed_args if isinstance(parsed_args, dict) else {}

                normalized.append(
                    {
                        "id": raw_tc.get("id"),
                        "name": name or "unknown",
                        "args": args if isinstance(args, dict) else {},
                    }
                )

        for invalid_tc in getattr(msg, "invalid_tool_calls", None) or []:
            if not isinstance(invalid_tc, dict):
                continue
            normalized.append(
                {
                    "id": invalid_tc.get("id"),
                    "name": invalid_tc.get("name") or "unknown",
                    "args": {},
                    "invalid": True,
                    "error": invalid_tc.get("error"),
                }
            )

        return normalized

    @staticmethod
    def _synthetic_tool_message_content(tool_call: dict[str, Any]) -> str:
        """Build the synthetic ToolMessage content for a dangling tool call."""
        if tool_call.get("invalid"):
            name = tool_call.get("name")
            error = tool_call.get("error")
            error_text = _cap_error_detail(error)
            if name == "write_file":
                details = f" Parser error: {error_text}" if error_text else ""
                return _WRITE_FILE_PRESCRIPTION.format(details=details)
            if error_text:
                return _GENERIC_RECOVERY_WITH_DETAIL.format(error_text=error_text)
            return _GENERIC_RECOVERY_NO_DETAIL
        return _INTERRUPTED_FALLBACK

    def _build_patched_messages(
        self, messages: Sequence[BaseMessage]
    ) -> list[BaseMessage] | None:
        """Re-group messages so each ``AIMessage.tool_call[i]`` has an adjacent ToolMessage.

        Returns the patched list, or ``None`` when no changes are
        needed. Each ``AIMessage`` declares some tool_call ids;
        matched results (by ``tool_call_id``) are popped from the
        queue in order; any remaining ids get a synthetic
        ``ToolMessage(status='error', ...)`` inserted immediately
        after the AIMessage.
        """
        tool_messages_by_id: dict[str, deque[ToolMessage]] = defaultdict(deque)
        for msg in messages:
            if isinstance(msg, ToolMessage):
                tool_messages_by_id[msg.tool_call_id].append(msg)

        tool_call_ids: set[str] = set()
        for msg in messages:
            if not isinstance(msg, AIMessage):
                continue
            for tc in self._message_tool_calls(msg):
                tc_id = tc.get("id")
                if tc_id:
                    tool_call_ids.add(tc_id)

        patched: list[BaseMessage] = []
        patch_count = 0
        for msg in messages:
            if isinstance(msg, ToolMessage) and msg.tool_call_id in tool_call_ids:
                # The ToolMessage will be re-emitted adjacent to its
                # dispatch AIMessage further down; skip it here.
                continue

            patched.append(msg)
            if not isinstance(msg, AIMessage):
                continue

            for tc in self._message_tool_calls(msg):
                tc_id = tc.get("id")
                if not tc_id:
                    continue

                tool_msg_queue = tool_messages_by_id.get(tc_id)
                existing_tool_msg = tool_msg_queue.popleft() if tool_msg_queue else None
                if existing_tool_msg is not None:
                    patched.append(existing_tool_msg)
                else:
                    patched.append(
                        ToolMessage(
                            content=self._synthetic_tool_message_content(tc),
                            tool_call_id=tc_id,
                            name=tc.get("name", "unknown"),
                            status="error",
                        )
                    )
                    patch_count += 1

        if patched == list(messages):
            return None

        if patch_count:
            logger.warning(
                "Injecting %d placeholder ToolMessage(s) for dangling tool calls",
                patch_count,
            )
        return patched

    # ── wrap hooks ───────────────────────────────────────────────

    @override
    def wrap_model_call(
        self,
        request: ModelCallRequest,
        handler: Callable[[ModelCallRequest], Any],
    ) -> Any:
        patched = self._build_patched_messages(request.messages)
        if patched is not None:
            request.messages = patched
        return handler(request)

    @override
    async def awrap_model_call(
        self,
        request: ModelCallRequest,
        handler: Callable[[ModelCallRequest], Awaitable[Any]],
    ) -> Any:
        patched = self._build_patched_messages(request.messages)
        if patched is not None:
            request.messages = patched
        return await handler(request)


__all__ = [
    "_MAX_RECOVERY_ERROR_DETAIL_LEN",
    "DanglingToolCallMiddleware",
]
