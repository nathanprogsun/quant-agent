"""LangGraph chunk serialization utilities."""

from __future__ import annotations

from typing import Any


def serialize_langgraph_chunk(
    item: Any,
    stream_modes: list[str] | None = None,
) -> tuple[str, Any]:
    """Parse LangGraph astream output into (mode, data).

    Handles three formats:
    - 2-tuple: (mode, data) — standard
    - 3-tuple: (namespace, mode, data) — subgraph
    - single value: data — defaults to "values" mode

    Args:
        item: Raw chunk from agent.astream().
        stream_modes: Accepted mode names. If set, non-matching modes
            are wrapped as "values".

    Returns:
        (mode, data) tuple.
    """
    if isinstance(item, tuple):
        if len(item) == 3:
            _, mode, data = item
            if not stream_modes or mode in stream_modes:
                return mode, data
        elif len(item) == 2:
            mode, data = item
            if not stream_modes or mode in stream_modes:
                return mode, data
    return "values", item
