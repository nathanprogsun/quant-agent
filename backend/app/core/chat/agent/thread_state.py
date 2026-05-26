"""LangGraph state schema for chat threads."""

from __future__ import annotations

from typing import Annotated, Any, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph import add_messages


def merge_artifacts(existing: list[str], new: list[str]) -> list[str]:
    """Merge artifact paths, deduplicating by value."""
    seen = set(existing)
    merged = list(existing)
    for item in new:
        if item not in seen:
            merged.append(item)
            seen.add(item)
    return merged


class ThreadState(TypedDict, total=False):
    """LangGraph state schema.

    total=False allows all fields to be optional.
    Phase 1 uses only messages + title.
    Other fields are reserved for future phases.
    """

    messages: Annotated[list[BaseMessage], add_messages]  # P0
    title: str | None  # P0
    artifacts: Annotated[list[str], merge_artifacts]  # P3
    todos: list[dict] | None  # P4: Plan mode
    uploaded_files: list[dict] | None  # P3
    code: str | None  # P0 (quant): strategy code
    session_status: str | None  # P0 (quant): session state machine
