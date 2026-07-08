"""Token usage tracking middleware.

Accumulates token counts from the most recent model response and, when a
``task`` tool dispatched a subagent, attributes the subagent's token usage
back to the parent dispatch ``AIMessage`` via a reverse walk (P3.4).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, NotRequired, override

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from langgraph.runtime import Runtime

from app.core.chat.tools.builtin.task_tool import pop_cached_subagent_usage


class TokenUsageMiddlewareState(AgentState):
    """State written by :class:`TokenUsageMiddleware`."""

    token_usage: NotRequired[dict[str, int]]


def _has_tool_call(message: AIMessage, tool_call_id: str) -> bool:
    """Return True if ``message`` contains a tool_call with the given id."""
    for tc in message.tool_calls or []:
        # LangChain's typed ToolCall always has ``id`` here (per TypedDict), but
        # at runtime some providers still pass plain dicts, hence the duck read.
        tc_id: str | None = getattr(tc, "id", None) if hasattr(tc, "id") else tc.get("id")
        if tc_id == tool_call_id:
            return True
    return False


def _walk_dispatch(
    messages: Sequence[BaseMessage],
    tool_msg_idx: int,
    tool_call_id: str,
) -> AIMessage | None:
    """Walk backward from ``messages[tool_msg_idx]`` to the dispatch AIMessage."""
    dispatch_idx = tool_msg_idx - 1
    while dispatch_idx >= 0:
        candidate = messages[dispatch_idx]
        if isinstance(candidate, AIMessage) and _has_tool_call(candidate, tool_call_id):
            return candidate
        dispatch_idx -= 1
    return None


def _reverse_walk_subagent_usage(messages: Sequence[BaseMessage]) -> dict[int, AIMessage]:
    """Reverse-walk consecutive ``ToolMessage``s to attribute subagent usage.

    Mirrors deer-flow's token_usage_middleware._apply:282-314. For each
    ToolMessage with a tool_call_id, pop the cached subagent usage (if any),
    find the dispatch AIMessage via _has_tool_call, and merge into
    ``state_updates[idx]`` for downstream usage accumulation.
    """
    state_updates: dict[int, AIMessage] = {}
    if len(messages) < 2:
        return state_updates

    idx = len(messages) - 2  # Skip the final AIMessage (the model response)
    while idx >= 0:
        msg = messages[idx]
        if not isinstance(msg, ToolMessage) or not msg.tool_call_id:
            idx -= 1
            continue
        usage = pop_cached_subagent_usage(msg.tool_call_id)
        if usage:
            dispatch = _walk_dispatch(messages, idx, msg.tool_call_id)
            if dispatch is not None:
                existing = state_updates.get(id(dispatch))
                prev: dict[str, int] = _as_dict(
                    existing.usage_metadata
                    if existing is not None
                    else getattr(dispatch, "usage_metadata", None)
                )
                merged: dict[str, int] = {
                    **prev,
                    "input_tokens": prev.get("input_tokens", 0) + usage["input_tokens"],
                    "output_tokens": prev.get("output_tokens", 0) + usage["output_tokens"],
                    "total_tokens": prev.get("total_tokens", 0) + usage["total_tokens"],
                }
                state_updates[id(dispatch)] = dispatch.model_copy(update={"usage_metadata": merged})
        idx -= 1
    return state_updates


def _as_dict(metadata: Any) -> dict[str, int]:
    """Normalize usage_metadata (dict | None) to a plain dict[str, int]."""
    if metadata is None:
        return {}
    if isinstance(metadata, dict):
        return {k: int(v) for k, v in metadata.items() if isinstance(v, (int, float))}
    # Pydantic v2 model — convert via model_dump with include=ints
    if hasattr(metadata, "model_dump"):
        return {k: int(v) for k, v in metadata.model_dump().items() if isinstance(v, (int, float))}
    return dict(metadata) if metadata else {}


class TokenUsageMiddleware(AgentMiddleware[TokenUsageMiddlewareState]):
    """Tracks token usage across the conversation.

    Accumulates token counts from model responses. When a task tool has
    dispatched a subagent that completed between model calls, this
    middleware attribute-walks back through messages[].message_to dispatch
    AIMessage and merges the cached subagent usage into its usage_metadata.
    """

    def __init__(self) -> None:
        self._total_tokens = 0
        self._prompt_tokens = 0
        self._completion_tokens = 0
        self._turn_count = 0

    @override
    async def aafter_model(self, state: TokenUsageMiddlewareState, runtime: Runtime) -> dict[str, Any] | None:
        """Extract usage from the latest model response and bridge subagent usage."""
        messages = list(state.get("messages", []))
        if not messages:
            return {
                "token_usage": self._as_state_dict(),
            }

        # P3.4 reverse walk — collect ALL updates for dispatch messages
        subagent_updates = _reverse_walk_subagent_usage(messages)

        last_message = messages[-1]
        usage = getattr(last_message, "usage", None)
        if usage:
            self._prompt_tokens += getattr(usage, "prompt_tokens", 0)
            self._completion_tokens += getattr(usage, "completion_tokens", 0)
            self._total_tokens += getattr(usage, "total_tokens", 0)
            self._turn_count += 1

        out: dict[str, Any] = {"token_usage": self._as_state_dict()}
        # If subagent updates were found, surface them as message patches so
        # the add_messages reducer replaces the dispatch AIMessage in-place by id.
        if subagent_updates:
            # Deduplicate: multiple ToolMessages may target the same dispatch AIMessage
            seen_ids: dict[str, bool] = {}
            result: list[BaseMessage] = []
            for m in messages:
                if id(m) in subagent_updates:
                    patched = subagent_updates[id(m)]
                    msg_id = patched.id or ""
                    if msg_id not in seen_ids:
                        seen_ids[msg_id] = True
                        result.append(patched)
                else:
                    result.append(m)
            out["messages"] = result
        return out

    def _as_state_dict(self) -> dict[str, int]:
        return {
            "prompt_tokens": self._prompt_tokens,
            "completion_tokens": self._completion_tokens,
            "total_tokens": self._total_tokens,
            "turn_count": self._turn_count,
        }

    def get_usage_stats(self) -> dict[str, int]:
        return self._as_state_dict()

    def reset(self) -> None:
        self._total_tokens = 0
        self._prompt_tokens = 0
        self._completion_tokens = 0
        self._turn_count = 0
