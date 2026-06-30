"""Task tool — delegates work to subagents via the persistent isolated loop.

Ports deer-flow's tools/builtins/task_tool.py:33-51, 187, 340, 351:
- ``@tool('task')`` surface (replaces the BaseTool stub)
- ``InjectedToolCallId`` injection so the parent dispatch id is reused
  as the subagent ``task_id`` (P3.4 bridge consumes this id)
- delegation via ``SubagentExecutor.execute_async`` onto the persistent
  isolated loop (3.1)
- stream events via ``get_stream_writer()``: ``task_started``,
  ``task_running``, ``task_completed`` (etc.)
- on ``CancelledError``, ``_subagent_usage_cache`` entry is popped so
  the parent ``TokenUsageMiddleware`` does not accumulate a phantom bucket
- config resolution uses the real ``SubagentsAppConfig`` (P3.5 port of
  deer-flow's ``config/subagents_config.py:71-143``) so per-agent timeout /
  max-turns overrides are honored
- channel-level ``subagent_enabled`` is honored via ``Settings.subagent_enabled``

Adapter: quant-agent does not run a runtime ``deerflow.tools.types.Runtime``
injected into the langchain tool call; instead we accept the standard
``InjectedToolCallId`` parameter via the langchain-core Annotated surface.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Annotated, Any

from langchain_core.tools import InjectedToolCallId, tool
from langgraph.config import get_stream_writer

from app.config.subagents_config import SubagentsAppConfig
from app.core.chat.subagents.executor import (
    MAX_CONCURRENT_SUBAGENTS,
    SubagentExecutor,
    SubagentResult,
    SubagentStatus,
    cleanup_background_task,
    get_background_task_result,
)
from app.settings import get_settings

logger = logging.getLogger(__name__)

# Per-tool_call_id usage cache. Populated by ``_cache_subagent_usage`` on
# terminal status; cleared on cancel/exception; consumed by
# ``TokenUsageMiddleware._apply`` (P3.4 bridge) to attribute tokens to the
# parent dispatch AIMessage.
_subagent_usage_cache: dict[str, dict[str, int]] = {}


def pop_cached_subagent_usage(tool_call_id: str) -> dict[str, int] | None:
    """Remove and return the cached usage dict for ``tool_call_id``."""
    return _subagent_usage_cache.pop(tool_call_id, None)


def _cache_subagent_usage(tool_call_id: str, usage: dict[str, int] | None) -> None:
    if usage:
        _subagent_usage_cache[tool_call_id] = usage


def _summarize_usage(records: list[dict[str, Any]] | None) -> dict[str, int] | None:
    if not records:
        return None
    return {
        "input_tokens": sum(r.get("input_tokens", 0) or 0 for r in records),
        "output_tokens": sum(r.get("output_tokens", 0) or 0 for r in records),
        "total_tokens": sum(r.get("total_tokens", 0) or 0 for r in records),
    }


@dataclass(frozen=True)
class ResolvedSubagentConfig:
    """Resolved effective settings for a subagent invocation.

    Mirrors the field set SubagentExecutor cares about (timeout, max_turns)
    plus the model name to bind. Resolution rules:
    - per-agent override (SubagentsAppConfig.agents[name]) wins over global
    - if neither override is set, builtin defaults apply
    """

    timeout_seconds: int
    max_turns: int | None
    model: str | None


def _resolve_subagent_config(name: str) -> ResolvedSubagentConfig:
    """Resolve the effective config for ``name`` using live settings."""
    settings = get_settings()
    app_cfg: SubagentsAppConfig = settings.subagents
    return ResolvedSubagentConfig(
        timeout_seconds=app_cfg.get_timeout_for(name),
        max_turns=app_cfg.get_max_turns_for(name, builtin_default=25),
        model=app_cfg.get_model_for(name),
    )


def _channel_subagent_enabled() -> bool:
    """Return the channel-level gate from settings.

    Per-request overrides via ``configurable.subagent_enabled`` are read by
    the lead-agent middleware chain; this tool only consults the global
    channel-level flag so the boot-time default applies uniformly.
    """
    return bool(get_settings().subagent_enabled)


async def _run_task_body(
    *,
    executor: SubagentExecutor,
    prompt: str,
    tool_call_id: str,
    config: ResolvedSubagentConfig,
    description: str,
    subagent_type: str,
) -> str:
    """Drive one subagent from spawn to terminal status; emit stream events.

    Kept as a module-level coroutine so tests can monkeypatch easily.
    """
    task_id = executor.execute_async(prompt, task_id=tool_call_id)
    writer = get_stream_writer()
    writer({"type": "task_started", "task_id": task_id, "description": description})
    last_message_count = 0
    try:
        while True:
            result = get_background_task_result(task_id)
            if result is None:
                writer({"type": "task_failed", "task_id": task_id, "error": "Task disappeared"})
                cleanup_background_task(task_id)
                return f"Error: Task {task_id} disappeared from background tasks"

            ai_messages = result.ai_messages or []
            current_message_count = len(ai_messages)
            if current_message_count > last_message_count:
                for i in range(last_message_count, current_message_count):
                    writer(
                        {
                            "type": "task_running",
                            "task_id": task_id,
                            "message": ai_messages[i],
                            "message_index": i + 1,
                            "total_messages": current_message_count,
                        }
                    )
                last_message_count = current_message_count

            usage = _summarize_usage(getattr(result, "token_usage_records", None))

            if result.status == SubagentStatus.COMPLETED:
                _cache_subagent_usage(tool_call_id, usage)
                writer(
                    {
                        "type": "task_completed",
                        "task_id": task_id,
                        "result": result.result,
                        "usage": usage,
                    }
                )
                cleanup_background_task(task_id)
                return f"Task Succeeded. Result: {result.result}"
            if result.status == SubagentStatus.FAILED:
                _cache_subagent_usage(tool_call_id, usage)
                writer(
                    {
                        "type": "task_failed",
                        "task_id": task_id,
                        "error": result.error,
                        "usage": usage,
                    }
                )
                cleanup_background_task(task_id)
                return f"Task failed. Error: {result.error}"
            if result.status == SubagentStatus.CANCELLED:
                _cache_subagent_usage(tool_call_id, usage)
                writer(
                    {
                        "type": "task_cancelled",
                        "task_id": task_id,
                        "error": result.error,
                        "usage": usage,
                    }
                )
                cleanup_background_task(task_id)
                return "Task cancelled by user."
            if result.status == SubagentStatus.TIMED_OUT:
                _cache_subagent_usage(tool_call_id, usage)
                writer(
                    {
                        "type": "task_timed_out",
                        "task_id": task_id,
                        "error": result.error,
                        "usage": usage,
                    }
                )
                cleanup_background_task(task_id)
                return f"Task timed out. Error: {result.error}"

            await asyncio.sleep(5)
    except asyncio.CancelledError:
        _subagent_usage_cache.pop(tool_call_id, None)
        raise


@tool("task", parse_docstring=True)
async def task_tool(
    description: str,
    prompt: str,
    subagent_type: str,
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> str:
    """Delegate a task to a specialized subagent that runs in its own context.

    Args:
        description: A short (3-5 word) description of the task for logging/display.
        prompt: The task description for the subagent. Be specific.
        subagent_type: The subagent type to use (e.g. ``general-purpose``).
        tool_call_id: Injected by the framework — the parent dispatch tool id
            reused as the subagent task id for downstream attribution.

    Honors the channel-level ``Settings.subagent_enabled`` gate: when False
    the tool returns an explanatory error instead of dispatching. Per-agent
    overrides (timeout, max_turns, model) are resolved through
    ``SubagentsAppConfig`` rather than the previous duck-typed stub.
    """
    if not _channel_subagent_enabled():
        return "Error: Subagents are disabled for this session (Settings.subagent_enabled=False)."

    config = _resolve_subagent_config(subagent_type)
    executor = SubagentExecutor(
        name=subagent_type,
        prompt=prompt,
        timeout_seconds=config.timeout_seconds,
        max_turns=config.max_turns,
    )
    return await _run_task_body(
        executor=executor,
        prompt=prompt,
        tool_call_id=tool_call_id,
        config=config,
        description=description,
        subagent_type=subagent_type,
    )


# Public alias — backward-compat for ``app.core.chat.tools.__init__``.
TaskTool = task_tool


__all__ = [
    "MAX_CONCURRENT_SUBAGENTS",
    "ResolvedSubagentConfig",
    "SubagentExecutor",
    "SubagentResult",
    "SubagentStatus",
    "TaskTool",
    "_subagent_usage_cache",
    "pop_cached_subagent_usage",
    "task_tool",
]
