"""Helpers for mapping SDK stream modes to LangGraph stream modes."""

from __future__ import annotations

DEFAULT_STREAM_MODES = ["values", "messages-tuple"]


def normalize_request_stream_modes(requested: list[str] | None) -> list[str]:
    """Normalize client-requested stream modes with project defaults."""
    modes = list(requested or DEFAULT_STREAM_MODES)
    if not modes:
        return list(DEFAULT_STREAM_MODES)
    return modes


def resolve_langgraph_stream_modes(requested: list[str] | None) -> list[str]:
    """Map LangGraph SDK stream mode names to LangGraph astream modes."""
    resolved: list[str] = []
    for mode in normalize_request_stream_modes(requested):
        langgraph_mode = "messages" if mode == "messages-tuple" else mode
        if langgraph_mode not in resolved:
            resolved.append(langgraph_mode)
    return resolved or ["values"]
