"""Unit tests for stream mode helpers."""

from app.core.chat.service.stream_modes import (
    DEFAULT_STREAM_MODES,
    normalize_request_stream_modes,
    resolve_langgraph_stream_modes,
)


def test_default_stream_modes_include_messages_tuple() -> None:
    assert DEFAULT_STREAM_MODES == ["values", "messages-tuple"]


def test_normalize_request_stream_modes_uses_defaults() -> None:
    assert normalize_request_stream_modes(None) == ["values", "messages-tuple"]


def test_resolve_langgraph_stream_modes_maps_messages_tuple() -> None:
    assert resolve_langgraph_stream_modes(["values", "messages-tuple"]) == [
        "values",
        "messages",
        "custom",
    ]
