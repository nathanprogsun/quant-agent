"""Subagent subsystem — persistent isolated event loop + executor scaffolding."""

from __future__ import annotations

from app.core.chat.subagents.executor import (
    MAX_CONCURRENT_SUBAGENTS,
    SubagentExecutor,
    SubagentResult,
    SubagentStatus,
    cleanup_background_task,
    get_background_task_result,
    list_background_tasks,
    request_cancel_background_task,
)

__all__ = [
    "MAX_CONCURRENT_SUBAGENTS",
    "SubagentExecutor",
    "SubagentResult",
    "SubagentStatus",
    "cleanup_background_task",
    "get_background_task_result",
    "list_background_tasks",
    "request_cancel_background_task",
]
