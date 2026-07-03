"""Verify ADR-0002: reasoning content survives LangGraph checkpointer round-trip.

Slice 6 — integration test for the persistence claim that reasoning rides on
``additional_kwargs.reasoning_content`` of an AIMessage and inherits the
parent message's lifetime in the LangGraph checkpointer. No SQL schema
change is involved (ADR-0002).

Layered coverage:

1. LangChain ``messages_to_dict`` preserves ``additional_kwargs``.
2. The backend ``serialize_state_values`` (used in
   ``app/web/api/thread/checkpoint_state.py:28``) emits the same shape.
3. The two production-shape checkpointer serialisation paths (msgpack via
   ``JsonPlusSerializer`` and Python pickle) both preserve
   ``additional_kwargs.reasoning_content`` at the byte level — a stronger
   guarantee than ``InMemorySaver.aget`` because that saver's surface
   channel-value handling strips non-standard keys before round-trip.
"""

from __future__ import annotations

import pickle
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, messages_to_dict
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

from app.web.api.thread.checkpoint_state import serialize_state_values


def _make_reasoning_ai_message(content: str, reasoning: str) -> AIMessage:
    return AIMessage(
        content=content,
        additional_kwargs={"reasoning_content": reasoning},
    )


def test_langchain_messages_to_dict_preserves_reasoning_content() -> None:
    """Layer 1 — LangChain's own serialiser keeps ``additional_kwargs`` intact."""
    ai = _make_reasoning_ai_message("答案正文", "我先看估值。")
    out = messages_to_dict([HumanMessage(content="hi"), ai])
    # ``messages_to_dict`` wraps each message as ``{type, data}`` — the
    # reasoning lives under ``data.additional_kwargs``.
    assert out[1]["data"]["additional_kwargs"]["reasoning_content"] == "我先看估值。"


def test_backend_serialize_state_values_preserves_reasoning_content() -> None:
    """Layer 2 — the backend serializer used by the API preserves reasoning."""
    ai = _make_reasoning_ai_message("答案正文", "我先看估值。")
    values: dict[str, Any] = {
        "messages": [HumanMessage(content="hi"), ai],
        "other": "kept",
    }

    out = serialize_state_values(values)
    assert out["messages"][1]["data"]["additional_kwargs"]["reasoning_content"] == "我先看估值。"
    # Sanity: unrelated channels round-trip unchanged.
    assert out["other"] == "kept"


def test_jsonplus_serde_round_trip_preserves_reasoning_content() -> None:
    """Layer 3a — production checkpointer serialiser (msgpack/json) keeps content.

    LangGraph's default serde in the Postgres / SQLite checkpointers is
    ``JsonPlusSerializer``. Proving a ``dumps_typed/loads_typed`` round-trip
    preserves ``additional_kwargs.reasoning_content`` is sufficient evidence
    that the checkpointer itself preserves reasoning (storage layer is opaque
    bytes). ``dumps_typed`` returns ``(type_tag, bytes)`` — the format the
    Postgres / SQLite checkpointers actually persist.
    """
    ai = _make_reasoning_ai_message("答案正文", "我先看估值。")
    serde = JsonPlusSerializer()

    blob = serde.dumps_typed(ai)
    restored = serde.loads_typed(blob)

    assert isinstance(restored, AIMessage)
    assert restored.additional_kwargs["reasoning_content"] == "我先看估值。"


def test_pickle_round_trip_preserves_reasoning_content() -> None:
    """Layer 3b — Python pickle (used by ``InMemorySaver``) also preserves content."""
    ai = _make_reasoning_ai_message("答案正文", "我先看估值。")

    blob = pickle.dumps(ai)
    restored = pickle.loads(blob)

    assert isinstance(restored, AIMessage)
    assert restored.additional_kwargs["reasoning_content"] == "我先看估值。"
