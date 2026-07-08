"""Reasoning chunk normaliser.

The provider adapter (``patched_chat.py``) iterates each streamed
``AIMessageChunk`` and delegates reasoning extraction to this module. Each
chunk typically carries *zero or more* reasoning carries; this normaliser
returns exactly the structured result that the adapter will merge into
``AIMessageChunk.additional_kwargs["reasoning_content"]``.

The five channels enumerated in ADR-0001 are detected in priority order:

1. ``delta.reasoning_content``  — DeepSeek / MiniMax-style sibling of ``delta.content``
2. ``delta.reasoning``          — vLLM standardised alias
3. ``additional_kwargs.reasoning_details`` — sometimes populated by proxies
4. ``content[*].type == "thinking"`` content block — when the proxy emits structured
5. Inline ``«THINK»…«/THINK»`` tags inside ``content`` — defensive fallback

This module is intentionally pure: no I/O, no mutation of the chunk. Slice 0
ships only the public surface; provider branches arrive in slice 1.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum


class ReasoningChannel(StrEnum):
    """Where reasoning content was detected inside a streamed chunk."""

    DELTA_REASONING_CONTENT = "delta.reasoning_content"
    DELTA_REASONING = "delta.reasoning"
    DELTA_REASONING_DETAILS = "delta.reasoning_details"
    CONTENT_BLOCK_THINKING = "content_block.thinking"
    INLINE_THINK_TAGS = "inline_«THINK»_tags"
    NONE = "none"

    @property
    def appends(self) -> bool:
        """True if ``text`` for this channel is a per-chunk partial that must be concatenated.

        DeepSeek and vLLM emit cumulative ``delta.reasoning_content`` / ``delta.reasoning``
        so the local enricher can overwrite without losing data. MiniMax emits *partial*
        ``delta.reasoning_details`` per chunk — to reconstruct the full reasoning, the
        enricher must concatenate.
        """
        return self is ReasoningChannel.DELTA_REASONING_DETAILS


@dataclass(frozen=True, slots=True)
class ReasoningResult:
    """Outcome of inspecting one streamed chunk.

    Attributes:
        text: Reasoning text delta to merge into ``additional_kwargs.reasoning_content``.
            ``None`` means the chunk carried no reasoning this iteration.
        channel: Channel the text came from (or ``NONE``).
        raw_extracted: The verbatim extracted value, kept for tests; None when
            the chunk carried nothing.
    """

    text: str | None
    channel: ReasoningChannel
    raw_extracted: str | None


def normalize_reasoning_chunk(chunk: object) -> ReasoningResult:
    """Inspect one streamed chunk and return any reasoning text it carries.

    Slice 1 implements channel 1 (``delta.reasoning_content``) and channel 2
    (``delta.reasoning``). Channels 3-5 land in slices 4 and 5. Pure function:
    no mutation of the chunk.
    """

    delta = _resolve_delta(chunk)
    if isinstance(delta, dict):
        # Channel 1 — DeepSeek-style sibling of delta.content (cumulative upstream).
        value = delta.get("reasoning_content")
        if isinstance(value, str) and value.strip():
            return ReasoningResult(
                text=value,
                channel=ReasoningChannel.DELTA_REASONING_CONTENT,
                raw_extracted=value,
            )
        # Channel 2 — vLLM-standardised alias (cumulative upstream).
        value = delta.get("reasoning")
        if isinstance(value, str) and value.strip():
            return ReasoningResult(
                text=value,
                channel=ReasoningChannel.DELTA_REASONING,
                raw_extracted=value,
            )
        # Channel 3 — MiniMax delta.reasoning_details: list of ``{text: …}`` dicts.
        # Each chunk carries a *partial* slice; the enricher concatenates.
        details_text = _extract_reasoning_details_text(delta.get("reasoning_details"))
        if details_text is not None:
            return ReasoningResult(
                text=details_text,
                channel=ReasoningChannel.DELTA_REASONING_DETAILS,
                raw_extracted=details_text,
            )

    return ReasoningResult(text=None, channel=ReasoningChannel.NONE, raw_extracted=None)


def _extract_reasoning_details_text(value: object) -> str | None:
    """Flatten MiniMax's ``reasoning_details`` list into a single string.

    Returns ``None`` when the input is not a list, or when no item yields a
    non-empty text. Each item must be a Mapping with a string ``text`` field;
    everything else is skipped silently.
    """

    if not isinstance(value, list):
        return None
    parts: list[str] = []
    for item in value:
        if not isinstance(item, Mapping):
            continue
        text = item.get("text")
        if isinstance(text, str) and text.strip():
            parts.append(text)
    if not parts:
        return None
    return "\n\n".join(parts)


def _resolve_delta(chunk: object) -> object:
    """Return the delta field of ``chunk`` regardless of wrapper shape.

    Accepts: ``AIMessageChunk`` (delta on the chunk itself), ``ChatGenerationChunk``
    (delta one level deeper via ``.message``), and plain dicts.
    """

    direct = getattr(chunk, "delta", None)
    if direct is not None:
        return direct
    if isinstance(chunk, dict):
        return chunk.get("delta")
    message = getattr(chunk, "message", None)
    if message is not None:
        return getattr(message, "delta", None)
    return None


# ── enrich_chunk ────────────────────────────────────────────────────────────


def _resolve_additional_kwargs(chunk: object) -> dict[str, object] | None:
    """Return the mutable ``additional_kwargs`` dict on the chunk, if any.

    Returns ``None`` if the chunk has no mutable slot for it; the caller then
    must skip enrichment rather than crash.
    """

    direct = getattr(chunk, "additional_kwargs", None)
    if isinstance(direct, dict):
        return direct
    if isinstance(chunk, dict):
        ak = chunk.get("additional_kwargs")
        if isinstance(ak, dict):
            return ak
    return None


def enrich_chunk(chunk: object) -> ReasoningResult:
    """Promote detected reasoning into ``chunk.additional_kwargs.reasoning_content``.

    Mutates the chunk in place when an additional_kwargs slot is reachable.
    Returns the underlying ``ReasoningResult`` so callers can log or branch.

    Write semantics:
      - Most-recent-wins (cumulative channels like ``delta.reasoning_content`` /
        ``delta.reasoning``): upstream already accumulates — overwrite.
      - Append (partial channels like ``delta.reasoning_details``): upstream
        emits per-chunk slices — concatenate onto the existing
        ``reasoning_content`` value.
    """

    result = normalize_reasoning_chunk(chunk)
    if result.text is None:
        return result
    ak = _resolve_additional_kwargs(chunk)
    if ak is None:
        return result
    if result.channel.appends:
        existing = ak.get("reasoning_content")
        if isinstance(existing, str):
            ak["reasoning_content"] = f"{existing}{result.text}"
        else:
            ak["reasoning_content"] = result.text
    else:
        ak["reasoning_content"] = result.text
    return result


__all__ = [
    "ReasoningChannel",
    "ReasoningResult",
    "enrich_chunk",
    "normalize_reasoning_chunk",
]
