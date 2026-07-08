"""Unit tests for the mode-aware LangGraph chunk serializer.

Covers:
- ``serialize(obj, *, mode=)`` dispatch on stream mode.
- ``serialize_channel_values`` strips internal ``__pregel_*`` keys.
- ``strip_data_url_image_blocks`` drops ``data:``-scheme image_url blocks
  from ``hide_from_ui`` messages while preserving text / https images /
  ordering of non-hidden messages.
- ``serialize_messages_tuple`` handles ``(chunk, metadata)`` tuples.
"""

from __future__ import annotations

from langchain_core.messages import AIMessageChunk, HumanMessage

from app.common.serialization import (
    serialize,
    serialize_channel_values,
    serialize_messages_tuple,
    strip_data_url_image_blocks,
)


def _msg_dict(content: object, *, hide_from_ui: bool = False, mid: str = "m1") -> dict:
    kw: dict = {}
    if hide_from_ui:
        kw["hide_from_ui"] = True
    return {
        "id": mid,
        "type": "human",
        "content": content,
        "additional_kwargs": kw,
    }


class TestSerializePrimitivesAndContainers:
    def test_none(self) -> None:
        assert serialize(None) is None

    def test_scalars_passthrough(self) -> None:
        assert serialize("x") == "x"
        assert serialize(1) == 1
        assert serialize(1.5) == 1.5
        assert serialize(True) is True

    def test_list_and_tuple_become_list(self) -> None:
        assert serialize([1, 2]) == [1, 2]
        assert serialize((1, 2)) == [1, 2]

    def test_dict_recurses(self) -> None:
        assert serialize({"a": [1, {"b": 2}]}) == {"a": [1, {"b": 2}]}


class TestSerializeModelDumpFallback:
    def test_pydantic_message_is_dumped(self) -> None:
        msg = AIMessageChunk(content="hello")
        out = serialize(msg)
        assert isinstance(out, dict)
        assert out["content"] == "hello"
        assert out["type"] == "AIMessageChunk"


class TestSerializeMessagesMode:
    def test_two_tuple_becomes_list(self) -> None:
        chunk = AIMessageChunk(content="hi")
        metadata = {"langgraph_node": "model"}
        out = serialize((chunk, metadata), mode="messages")
        assert isinstance(out, list)
        assert len(out) == 2
        assert out[0]["content"] == "hi"
        assert out[1] == metadata

    def test_non_tuple_falls_back_to_object_serialize(self) -> None:
        msg = AIMessageChunk(content="lo")
        out = serialize(msg, mode="messages")
        assert isinstance(out, dict)
        assert out["content"] == "lo"


class TestSerializeMessagesTupleDirect:
    def test_round_trip(self) -> None:
        chunk = AIMessageChunk(content="hi")
        out = serialize_messages_tuple((chunk, {"x": 1}))
        assert isinstance(out, list)
        assert out[0]["content"] == "hi"
        assert out[1] == {"x": 1}

    def test_non_tuple_passes_through(self) -> None:
        assert serialize_messages_tuple("plain") == "plain"


class TestSerializeChannelValues:
    def test_strips_pregel_keys(self) -> None:
        cv = {"messages": [], "__pregel_node": "x", "__pregel_step": 1, "title": "t"}
        out = serialize_channel_values(cv)
        assert "__pregel_node" not in out
        assert "__pregel_step" not in out
        assert out["title"] == "t"

    def test_recursively_serializes_values(self) -> None:
        msg = HumanMessage(content="hi")
        cv = {"messages": [msg], "__pregel_x": 1}
        out = serialize_channel_values(cv)
        assert isinstance(out["messages"], list)
        assert out["messages"][0]["content"] == "hi"


class TestStripDataUrlImageBlocks:
    def test_strips_data_url_from_hidden_message(self) -> None:
        msgs = [
            _msg_dict(
                [
                    {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}},
                    {"type": "text", "text": "kept"},
                ],
                hide_from_ui=True,
            )
        ]
        out = strip_data_url_image_blocks(msgs)
        assert len(out) == 1
        content = out[0]["content"]
        assert all(block.get("type") != "image_url" for block in content)
        assert any(block.get("type") == "text" for block in content)

    def test_keeps_https_image_url_in_hidden_message(self) -> None:
        msgs = [
            _msg_dict(
                [{"type": "image_url", "image_url": {"url": "https://x/y.png"}}],
                hide_from_ui=True,
            )
        ]
        out = strip_data_url_image_blocks(msgs)
        assert out[0]["content"][0]["image_url"]["url"] == "https://x/y.png"

    def test_leaves_non_hidden_messages_untouched(self) -> None:
        msgs = [
            _msg_dict(
                [{"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}}],
                hide_from_ui=False,
            )
        ]
        out = strip_data_url_image_blocks(msgs)
        assert out[0]["content"][0]["image_url"]["url"].startswith("data:")

    def test_preserves_count_and_order(self) -> None:
        msgs = [
            _msg_dict("plain", mid="a"),
            _msg_dict(
                [
                    {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}},
                    {"type": "text", "text": "t"},
                ],
                hide_from_ui=True,
                mid="b",
            ),
            _msg_dict("plain2", mid="c"),
        ]
        out = strip_data_url_image_blocks(msgs)
        assert [m["id"] for m in out] == ["a", "b", "c"]

    def test_handles_non_list_content(self) -> None:
        msgs = [_msg_dict("just text", hide_from_ui=True)]
        out = strip_data_url_image_blocks(msgs)
        assert out[0]["content"] == "just text"

    def test_handles_non_dict_messages(self) -> None:
        out = strip_data_url_image_blocks(["raw", None, 42])
        assert out == ["raw", None, 42]


class TestSerializeValuesMode:
    def test_values_mode_strips_pregel_and_image_blocks(self) -> None:
        cv = {
            "messages": [
                _msg_dict(
                    [
                        {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}},
                        {"type": "text", "text": "kept"},
                    ],
                    hide_from_ui=True,
                )
            ],
            "__pregel_node": "x",
            "title": "t",
        }
        out = serialize(cv, mode="values")
        assert "__pregel_node" not in out
        assert out["title"] == "t"
        assert all(block.get("type") != "image_url" for block in out["messages"][0]["content"])

    def test_values_mode_non_dict_passes_through(self) -> None:
        assert serialize("plain", mode="values") == "plain"
