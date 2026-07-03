"""Tests for ``PatchedChat`` — the provider adapter that surfaces reasoning deltas.

These tests bypass the real LangChain streaming by patching ``ChatOpenAI._stream``
so the focus stays on the adapter's behaviour rather than the OpenAI HTTP stack.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from unittest.mock import patch

from langchain_core.messages import AIMessage, HumanMessage
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from app.core.chat.llm.patched_chat import PatchedChat


@dataclass(slots=True)
class FakeChunk:
    delta: dict | None = None
    content: str = ""
    id: str = "msg_1"
    additional_kwargs: dict = field(default_factory=dict)


def test_patched_chat_is_a_chatopenai_subclass() -> None:
    """PatchedChat must be a drop-in replacement for ChatOpenAI."""
    assert issubclass(PatchedChat, ChatOpenAI)


def _make_chat() -> PatchedChat:
    return PatchedChat(
        model="test-model",
        api_key=SecretStr("sk-test-not-real"),
    )


def _patched_stream_with(chunks: list[FakeChunk]) -> Iterator[FakeChunk]:
    """Patch ``ChatOpenAI._stream`` to yield the supplied test chunks."""
    return iter(chunks)


def test_patched_chat_enriches_streamed_chunks_with_reasoning_content() -> None:
    """Each upstream chunk carrying delta.reasoning_content emerges with the field promoted."""
    chunks = [
        FakeChunk(delta={"reasoning_content": "step 1 reasoning"}),
        FakeChunk(delta={"reasoning_content": "step 2 reasoning"}),
        FakeChunk(delta={"content": "final answer"}),
    ]

    with patch.object(ChatOpenAI, "_stream", return_value=iter(chunks)):
        chat = _make_chat()
        out = list(chat._stream([HumanMessage(content="hi")]))

    assert out[0].additional_kwargs["reasoning_content"] == "step 1 reasoning"
    assert out[1].additional_kwargs["reasoning_content"] == "step 2 reasoning"
    # Final answer chunk: no reasoning extracted — additional_kwargs untouched.
    assert "reasoning_content" not in out[2].additional_kwargs


def test_patched_chat_passes_through_chunks_when_no_reasoning() -> None:
    """When the upstream stream carries no reasoning, the adapter is a no-op."""
    chunks = [
        FakeChunk(delta={"content": "Hello"}),
        FakeChunk(delta={"content": " world"}),
    ]

    with patch.object(ChatOpenAI, "_stream", return_value=iter(chunks)):
        chat = _make_chat()
        out = list(chat._stream([HumanMessage(content="hi")]))

    assert out == chunks
    assert all("reasoning_content" not in c.additional_kwargs for c in out)


def test_patched_chat_overrides_stream_method() -> None:
    """``PatchedChat._stream`` is defined locally (a behavioural override, not a passthrough)."""
    assert PatchedChat._stream.__qualname__.startswith("PatchedChat")


def test_patched_chat_concatenates_minimax_partial_reasoning_details() -> None:
    """Slice 4: chunks carrying ``delta.reasoning_details`` (MiniMax) accumulate.

    LangChain's chunk-merging is content-aware but ``additional_kwargs`` also
    carries forward via ``__add__``; we simulate that explicitly via the test
    fixture to verify the adapter's append-mode wiring.
    """

    chunks = [
        FakeChunk(delta={"reasoning_details": [{"text": "partial A"}]}),
        FakeChunk(delta={"reasoning_details": [{"text": "partial B"}]}),
    ]
    # Pre-seed the second chunk's additional_kwargs with the previous
    # accumulated reasoning_content to mirror LangChain's chunk merging.
    chunks[1].additional_kwargs = {"reasoning_content": "partial A"}

    with patch.object(ChatOpenAI, "_stream", return_value=iter(chunks)):
        chat = _make_chat()
        out = list(chat._stream([HumanMessage(content="hi")]))

    assert out[0].additional_kwargs["reasoning_content"] == "partial A"
    assert out[1].additional_kwargs["reasoning_content"] == "partial Apartial B"


# ── Slice 7: request-payload echo for MiniMax thinking mode ────────────────


def test_get_request_payload_injects_reasoning_content_on_assistant() -> None:
    """Multi-turn payload: assistant AIMessage's reasoning_content is echoed."""
    ai = AIMessage(
        content="final answer",
        additional_kwargs={"reasoning_content": "我先看估值。"},
    )
    base_payload = {
        "messages": [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "final answer"},
        ]
    }

    # We bypass ChatOpenAI._convert_input complexity by patching it directly.
    with patch.object(ChatOpenAI, "_get_request_payload", return_value=base_payload):
        chat = _make_chat()
        # The method calls _convert_input to get original_messages; this is
        # patched via the same ChatOpenAI mock since the parent class owns it.
        with patch.object(
            ChatOpenAI,
            "_convert_input",
            return_value=_FakeInput([HumanMessage(content="hi"), ai]),
        ):
            payload = chat._get_request_payload([HumanMessage(content="hi"), ai])

    assert payload["messages"][0]["role"] == "user"
    assert "reasoning_content" not in payload["messages"][0]
    assert payload["messages"][1]["role"] == "assistant"
    assert payload["messages"][1]["reasoning_content"] == "我先看估值。"


def test_get_request_payload_skips_assistant_without_reasoning() -> None:
    """When AIMessage has no reasoning_content, payload stays untouched."""
    ai = AIMessage(content="plain answer")
    base_payload = {
        "messages": [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "plain answer"},
        ]
    }
    with patch.object(ChatOpenAI, "_get_request_payload", return_value=base_payload):
        chat = _make_chat()
        with patch.object(
            ChatOpenAI,
            "_convert_input",
            return_value=_FakeInput([HumanMessage(content="hi"), ai]),
        ):
            payload = chat._get_request_payload([HumanMessage(content="hi"), ai])

    assert "reasoning_content" not in payload["messages"][1]
    assert payload["messages"][1]["content"] == "plain answer"


def test_get_request_payload_does_not_overwrite_existing_reasoning_content() -> None:
    """If the payload already carries reasoning_content (e.g. round-tripped), keep it."""
    ai = AIMessage(
        content="final answer",
        additional_kwargs={"reasoning_content": "newer thinking"},
    )
    base_payload = {
        "messages": [
            {"role": "user", "content": "hi"},
            {
                "role": "assistant",
                "content": "final answer",
                "reasoning_content": "already-set",
            },
        ]
    }
    with patch.object(ChatOpenAI, "_get_request_payload", return_value=base_payload):
        chat = _make_chat()
        with patch.object(
            ChatOpenAI,
            "_convert_input",
            return_value=_FakeInput([HumanMessage(content="hi"), ai]),
        ):
            payload = chat._get_request_payload([HumanMessage(content="hi"), ai])

    # The pre-existing value wins; the adapter respects whatever upstream chose.
    assert payload["messages"][1]["reasoning_content"] == "already-set"


def test_get_request_payload_handles_length_mismatch() -> None:
    """When payload length differs from source messages, match by counting assistant roles."""
    a1 = AIMessage(content="a1", additional_kwargs={"reasoning_content": "thinking 1"})
    a2 = AIMessage(content="a2", additional_kwargs={"reasoning_content": "thinking 2"})
    # Source has 1 user + 2 assistant; payload has 1 user + 1 assistant + 1 assistant.
    base_payload = {
        "messages": [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "a1"},
            {"role": "assistant", "content": "a2"},
        ]
    }
    source = [HumanMessage(content="hi"), a1, a2]
    with patch.object(ChatOpenAI, "_get_request_payload", return_value=base_payload):
        chat = _make_chat()
        with patch.object(ChatOpenAI, "_convert_input", return_value=_FakeInput(source)):
            payload = chat._get_request_payload(source)

    assert payload["messages"][1]["reasoning_content"] == "thinking 1"
    assert payload["messages"][2]["reasoning_content"] == "thinking 2"


# Helper class — ChatOpenAI._convert_input returns a PromptValue whose to_messages()
# returns the message list. Stand in for any PromptValue.
class _FakeInput:
    """Stand-in for the LangChain PromptValue returned by ``ChatOpenAI._convert_input``."""

    def __init__(self, messages: list) -> None:
        self._messages = messages

    def to_messages(self) -> list:
        return list(self._messages)
