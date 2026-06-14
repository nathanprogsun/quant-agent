"""Unit tests for stream mode helpers and worker serialization."""

from langchain_core.messages import AIMessageChunk

from app.core.chat.service.stream_modes import (
    DEFAULT_STREAM_MODES,
    normalize_request_stream_modes,
    resolve_langgraph_stream_modes,
)
from app.core.chat.service.worker import _prepare_publish_payload, _serialize_chunk_data


def test_default_stream_modes_include_messages_tuple() -> None:
    assert DEFAULT_STREAM_MODES == ["values", "messages-tuple"]


def test_normalize_request_stream_modes_uses_defaults() -> None:
    assert normalize_request_stream_modes(None) == ["values", "messages-tuple"]


def test_resolve_langgraph_stream_modes_maps_messages_tuple() -> None:
    assert resolve_langgraph_stream_modes(["values", "messages-tuple"]) == [
        "values",
        "messages",
    ]


def test_prepare_publish_payload_serializes_message_tuple() -> None:
    chunk = AIMessageChunk(content="你好", id="msg-1")
    metadata = {"langgraph_node": "agent"}

    event_name, payload = _prepare_publish_payload("messages", (chunk, metadata))

    assert event_name == "messages"
    assert isinstance(payload, list)
    assert len(payload) == 2
    assert payload[0]["content"] == "你好"
    assert payload[0]["type"] == "AIMessageChunk"
    assert payload[1]["langgraph_node"] == "agent"


def test_serialize_chunk_data_handles_nested_tuple() -> None:
    serialized = _serialize_chunk_data(("a", {"b": 1}))
    assert serialized == ["a", {"b": 1}]
