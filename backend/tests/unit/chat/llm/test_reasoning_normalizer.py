"""Skeleton tests for the reasoning chunk normaliser (slice 0).

Slice 0 ships only the public surface; the per-channel branches are added in
slice 1 (DeepSeek / MiniMax) and slice 5 (inline ``«THINK»`` tags).
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field

from app.core.chat.llm.reasoning_normalizer import (
    ReasoningChannel,
    ReasoningResult,
    enrich_chunk,
    normalize_reasoning_chunk,
)


def test_normalize_returns_empty_result_for_unknown_chunk() -> None:
    """Skeleton: any chunk returns None text and NONE channel until slice 1."""
    result = normalize_reasoning_chunk({})
    assert result == ReasoningResult(text=None, channel=ReasoningChannel.NONE, raw_extracted=None)


def test_normalize_does_not_mutate_chunk() -> None:
    """The normaliser is pure: input chunk must be left untouched."""
    chunk = {"delta": {"reasoning_content": "hello"}}
    snapshot = dict(chunk)
    normalize_reasoning_chunk(chunk)
    assert chunk == snapshot


def test_public_surface() -> None:
    """All five ADR-0001 channels are listed plus the NONE sentinel."""
    values = {c.value for c in ReasoningChannel}
    assert "delta.reasoning_content" in values
    assert "delta.reasoning" in values
    assert "delta.reasoning_details" in values
    assert "content_block.thinking" in values
    assert "inline_«THINK»_tags" in values
    assert "none" in values


def test_dataclass_is_frozen() -> None:
    """``ReasoningResult`` is frozen — no in-place mutation by callers."""
    result = ReasoningResult(
        text="x", channel=ReasoningChannel.DELTA_REASONING_CONTENT, raw_extracted="x"
    )

    try:
        result.text = "y"  # type: ignore[misc]
    except dataclasses.FrozenInstanceError:
        return
    raise AssertionError("ReasoningResult is not frozen")


# ── Slice 1: delta.reasoning_content + delta.reasoning channels ─────────────


@dataclass(slots=True)
class FakeChunk:
    """Mimics ChatGenerationChunk or AIMessageChunk for shape-only tests.

    The real langchain types are Pydantic models; this fake lets us assert the
    normaliser's duck-typed behaviour without invoking the chat model stack.
    """

    delta: dict | None = None
    additional_kwargs: dict = field(default_factory=dict)
    content: str | list | None = None
    message: object | None = None

    def __post_init__(self) -> None:
        if self.message is not None:
            # When ChatGenerationChunk shape, the inner message carries .delta and
            # additional_kwargs; expose via attribute lookups below.
            msg = self.message
            inner_delta = getattr(msg, "delta", None) or {}
            if inner_delta:
                self.delta = inner_delta
            inner_ak = getattr(msg, "additional_kwargs", None)
            if inner_ak is not None:
                self.additional_kwargs = inner_ak
            self.content = getattr(msg, "content", None)


def test_normalize_extracts_delta_reasoning_content_via_attribute() -> None:
    """Channel 1 — delta.reasoning_content on attribute-shaped chunk."""
    chunk = FakeChunk(delta={"reasoning_content": "thinking aloud"})
    result = normalize_reasoning_chunk(chunk)
    assert result.channel == ReasoningChannel.DELTA_REASONING_CONTENT
    assert result.text == "thinking aloud"
    assert result.raw_extracted == "thinking aloud"


def test_normalize_extracts_delta_reasoning_vllm_alias() -> None:
    """Channel 2 — delta.reasoning (vLLM standardised alias)."""
    chunk = FakeChunk(delta={"reasoning": "vllm thinks"})
    result = normalize_reasoning_chunk(chunk)
    assert result.channel == ReasoningChannel.DELTA_REASONING
    assert result.text == "vllm thinks"


def test_normalize_prefers_reasoning_content_over_reasoning() -> None:
    """When both fields appear, ``reasoning_content`` wins (DeepSeek precedence)."""
    chunk = FakeChunk(delta={"reasoning_content": "A", "reasoning": "B"})
    result = normalize_reasoning_chunk(chunk)
    assert result.channel == ReasoningChannel.DELTA_REASONING_CONTENT
    assert result.text == "A"


def test_normalize_extracts_delta_reasoning_content_via_dict() -> None:
    """Channel 1 — same field on a plain dict chunk (test shape parity)."""
    chunk = {"delta": {"reasoning_content": "from a dict"}}
    result = normalize_reasoning_chunk(chunk)
    assert result.channel == ReasoningChannel.DELTA_REASONING_CONTENT
    assert result.text == "from a dict"


def test_normalize_returns_none_for_empty_delta_reasoning() -> None:
    """An empty or whitespace-only payload is not a reasoning hit."""
    chunk = FakeChunk(delta={"reasoning_content": "", "content": "real text"})
    result = normalize_reasoning_chunk(chunk)
    assert result == ReasoningResult(text=None, channel=ReasoningChannel.NONE, raw_extracted=None)


def test_normalize_via_chat_generation_chunk_inner_message() -> None:
    """Channel 1 — when the chunk is a ChatGenerationChunk, look one level deeper."""

    @dataclass(slots=True)
    class InnerMessage:
        delta: dict
        additional_kwargs: dict
        content: str = ""

    inner = InnerMessage(delta={"reasoning_content": "from inner"}, additional_kwargs={})
    chunk = FakeChunk(message=inner)
    result = normalize_reasoning_chunk(chunk)
    assert result.channel == ReasoningChannel.DELTA_REASONING_CONTENT
    assert result.text == "from inner"


# ── Slice 1: enrich_chunk side-effect ───────────────────────────────────────


def test_enrich_chunk_promotes_into_additional_kwargs() -> None:
    """enrich_chunk writes the detected text into chunk.additional_kwargs.reasoning_content."""
    chunk = FakeChunk(delta={"reasoning_content": "promote me"})
    result = enrich_chunk(chunk)
    assert result.channel == ReasoningChannel.DELTA_REASONING_CONTENT
    assert result.text == "promote me"
    assert chunk.additional_kwargs == {"reasoning_content": "promote me"}


def test_enrich_chunk_no_reasoning_leaves_kwargs_intact() -> None:
    """When no reasoning is detected, additional_kwargs is not touched."""
    chunk = FakeChunk(delta={"content": "normal text"})
    chunk.additional_kwargs = {"existing": "value"}
    result = enrich_chunk(chunk)
    assert result.channel == ReasoningChannel.NONE
    assert chunk.additional_kwargs == {"existing": "value"}


def test_enrich_chunk_overwrites_previous_reasoning_value() -> None:
    """Most-recent-wins: each call replaces any prior reasoning_content value."""
    chunk = FakeChunk(delta={"reasoning_content": "second"})
    chunk.additional_kwargs = {"reasoning_content": "first"}
    enrich_chunk(chunk)
    assert chunk.additional_kwargs["reasoning_content"] == "second"


def test_enrich_chunk_handles_dict_shaped_chunk() -> None:
    """Dict-shaped chunks also receive additional_kwargs.reasoning_content."""
    chunk = {"delta": {"reasoning": "vllm text"}, "additional_kwargs": {}}
    enrich_chunk(chunk)
    assert chunk["additional_kwargs"]["reasoning_content"] == "vllm text"


# ── Slice 4: MiniMax delta.reasoning_details ────────────────────────────────


def test_normalize_extracts_delta_reasoning_details_list() -> None:
    """Channel: delta.reasoning_details — MiniMax emits a list of ``{text: …}`` dicts."""
    chunk = FakeChunk(delta={"reasoning_details": [{"text": "first part"}]})
    result = normalize_reasoning_chunk(chunk)
    assert result.channel == ReasoningChannel.DELTA_REASONING_DETAILS
    assert result.text == "first part"


def test_normalize_concatenates_multiple_reasoning_details_entries() -> None:
    """Multiple ``{text}`` items are joined with double-newline."""
    chunk = FakeChunk(
        delta={
            "reasoning_details": [
                {"text": "first"},
                {"text": "second"},
                {"text": "third"},
            ],
        },
    )
    result = normalize_reasoning_chunk(chunk)
    assert result.channel == ReasoningChannel.DELTA_REASONING_DETAILS
    assert result.text == "first\n\nsecond\n\nthird"


def test_normalize_skips_non_dict_items_in_reasoning_details() -> None:
    """Bizarre items that aren't dict-like are silently skipped."""
    chunk = FakeChunk(
        delta={
            "reasoning_details": [
                "stray string",
                42,
                None,
                {"text": "real"},
            ],
        },
    )
    result = normalize_reasoning_chunk(chunk)
    assert result.channel == ReasoningChannel.DELTA_REASONING_DETAILS
    assert result.text == "real"


def test_normalize_handles_empty_string_in_reasoning_details() -> None:
    """Empty ``text`` items are dropped (whitespace-only too)."""
    chunk = FakeChunk(
        delta={
            "reasoning_details": [
                {"text": ""},
                {"text": "   "},
                {"text": "kept"},
            ],
        },
    )
    result = normalize_reasoning_chunk(chunk)
    assert result.channel == ReasoningChannel.DELTA_REASONING_DETAILS
    assert result.text == "kept"


def test_normalize_returns_none_when_details_have_no_text() -> None:
    """If no entry yields a non-empty text, return None (no reasoning this chunk)."""
    chunk = FakeChunk(
        delta={"reasoning_details": [{"type": "summary"}, {"other": 1}]},
    )
    result = normalize_reasoning_chunk(chunk)
    assert result == ReasoningResult(text=None, channel=ReasoningChannel.NONE, raw_extracted=None)


def test_normalize_returns_none_when_reasoning_details_is_not_a_list() -> None:
    """Defensive: anything other than a list yields None (other channels don't pick it up)."""
    chunk = FakeChunk(delta={"reasoning_details": "unexpected string"})
    result = normalize_reasoning_chunk(chunk)
    assert result == ReasoningResult(text=None, channel=ReasoningChannel.NONE, raw_extracted=None)


def test_enrich_chunk_concatenates_appends_channels() -> None:
    """Channels whose text arrives in partial deltas must accumulate, not overwrite."""
    chunk = FakeChunk(delta={"reasoning_details": [{"text": "round 2"}]})
    chunk.additional_kwargs = {"reasoning_content": "round 1"}
    enrich_chunk(chunk)
    assert chunk.additional_kwargs["reasoning_content"] == "round 1round 2"


def test_enrich_chunk_concatenates_multiple_partial_reasoning_details_chunks() -> None:
    """Two-stream partial reasoning joins seamlessly across calls."""
    first = FakeChunk(delta={"reasoning_details": [{"text": "think "}]})
    first.additional_kwargs = {}
    enrich_chunk(first)
    assert first.additional_kwargs["reasoning_content"] == "think "

    second = FakeChunk(delta={"reasoning_details": [{"text": "harder"}]})
    # In a real LangChain stream each chunk would carry the previous
    # additional_kwargs through chunk merging; here we simulate that explicitly.
    second.additional_kwargs = {"reasoning_content": "think "}
    enrich_chunk(second)
    assert second.additional_kwargs["reasoning_content"] == "think harder"


def test_appendable_channel_set() -> None:
    """Only channels carrying partial per-chunk deltas are append-mode."""
    assert ReasoningChannel.DELTA_REASONING_DETAILS.appends is True
    assert ReasoningChannel.DELTA_REASONING_CONTENT.appends is False
    assert ReasoningChannel.DELTA_REASONING.appends is False
