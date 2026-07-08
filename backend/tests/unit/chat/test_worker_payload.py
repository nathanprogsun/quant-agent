"""Unit tests for the worker's stream-item unpacking and publish payload prep.

These tests pin the SSE wire format produced by the worker loop so the
single-mode fast path + mode-aware serializer refactor cannot drift it:

- ``messages`` events always carry ``[chunk_dump, metadata_dict]`` lists.
- ``values`` events carry the channel-values dict with ``__pregel_*`` keys
  stripped and ``data:`` image blocks dropped from ``hide_from_ui`` messages.
- ``custom`` events are surfaced as ``messages`` with a ``[chunk_dump, {}]``
  shape and carry the per-chunk message from ``get_stream_writer()``.
- ``_unpack_stream_item`` accepts 2-tuples, 3-tuples (subgraph), and bare
  values, defaulting to mode ``"values"``.
"""

from __future__ import annotations

from langchain_core.messages import AIMessageChunk

from app.core.chat.service.worker import _prepare_publish_payload, _unpack_stream_item


class TestUnpackStreamItem:
    def test_two_tuple(self) -> None:
        assert _unpack_stream_item(("messages", {"x": 1}), ["messages"]) == ("messages", {"x": 1})

    def test_three_tuple_subgraph(self) -> None:
        assert _unpack_stream_item(("ns", "values", {"y": 2}), ["values"]) == ("values", {"y": 2})

    def test_non_matching_mode_falls_back_to_values(self) -> None:
        # When a 2-tuple's mode isn't in requested modes, the helper falls
        # through to the "bare value" branch and returns the WHOLE item
        # (tuple included) under the "values" label. The worker never
        # raises on unexpected modes; it just relabels them as values.
        mode, data = _unpack_stream_item(("updates", {"z": 3}), ["values"])
        assert mode == "values"
        assert data == ("updates", {"z": 3})

    def test_bare_value_defaults_to_values(self) -> None:
        mode, data = _unpack_stream_item("plain", ["values"])
        assert mode == "values"
        assert data == "plain"


class TestPrepareMessagesPayload:
    def test_two_tuple_message(self) -> None:
        chunk = AIMessageChunk(content="hi")
        event, payload = _prepare_publish_payload("messages", (chunk, {"node": "model"}))
        assert event == "messages"
        assert isinstance(payload, list) and len(payload) == 2
        assert payload[0]["content"] == "hi"
        assert payload[1] == {"node": "model"}

    def test_two_list_message(self) -> None:
        chunk = AIMessageChunk(content="hi")
        event, payload = _prepare_publish_payload("messages", [chunk, {"node": "model"}])
        assert event == "messages"
        assert payload[0]["content"] == "hi"
        assert payload[1] == {"node": "model"}

    def test_non_tuple_message_falls_back_to_serialize(self) -> None:
        chunk = AIMessageChunk(content="lo")
        event, payload = _prepare_publish_payload("messages", chunk)
        # Non-tuple messages -> serializer returns a dict (model_dump)
        assert event == "messages"
        assert isinstance(payload, dict)
        assert payload["content"] == "lo"


class TestPrepareCustomPayload:
    def test_dict_with_messages_key(self) -> None:
        chunk = AIMessageChunk(content="custom-hi")
        data = {"messages": [chunk]}
        event, payload = _prepare_publish_payload("custom", data)
        assert event == "messages"
        assert isinstance(payload, list) and len(payload) == 2
        assert payload[0]["content"] == "custom-hi"
        assert payload[1] == {}

    def test_dict_without_messages_key(self) -> None:
        data = {"progress": "thinking"}
        event, payload = _prepare_publish_payload("custom", data)
        assert event == "messages"
        # Non-message dict -> serialize whole dict as chunk
        assert isinstance(payload, list) and len(payload) == 2
        assert payload[0] == {"progress": "thinking"}
        assert payload[1] == {}

    def test_bare_value(self) -> None:
        event, payload = _prepare_publish_payload("custom", "status-text")
        assert event == "messages"
        assert payload[0] == "status-text"
        assert payload[1] == {}


class TestPrepareValuesPayload:
    def test_strips_pregel_keys(self) -> None:
        data = {"messages": [], "__pregel_node": "x", "title": "t"}
        event, payload = _prepare_publish_payload("values", data)
        assert event == "values"
        assert isinstance(payload, dict)
        assert "__pregel_node" not in payload
        assert payload["title"] == "t"

    def test_strips_data_url_image_blocks_from_hidden_messages(self) -> None:
        msg = {
            "id": "m1",
            "type": "human",
            "content": [
                {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}},
                {"type": "text", "text": "kept"},
            ],
            "additional_kwargs": {"hide_from_ui": True},
        }
        data = {"messages": [msg], "__pregel_x": 1}
        event, payload = _prepare_publish_payload("values", data)
        assert event == "values"
        assert all(block.get("type") != "image_url" for block in payload["messages"][0]["content"])

    def test_keeps_https_image_blocks(self) -> None:
        msg = {
            "id": "m1",
            "type": "human",
            "content": [{"type": "image_url", "image_url": {"url": "https://x/y.png"}}],
            "additional_kwargs": {"hide_from_ui": True},
        }
        data = {"messages": [msg]}
        _event, payload = _prepare_publish_payload("values", data)
        assert payload["messages"][0]["content"][0]["image_url"]["url"] == "https://x/y.png"

    def test_non_dict_values_passes_through(self) -> None:
        event, payload = _prepare_publish_payload("values", "plain")
        assert event == "values"
        assert payload == "plain"


class TestPrepareOtherModes:
    def test_updates_mode_serializes_dict(self) -> None:
        event, payload = _prepare_publish_payload("updates", {"node": {"writes": 1}})
        assert event == "updates"
        assert payload == {"node": {"writes": 1}}
