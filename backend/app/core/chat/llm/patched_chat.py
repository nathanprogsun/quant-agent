"""``PatchedChat`` — a thin ``ChatOpenAI`` subclass that surfaces reasoning deltas.

Refer to ADR-0001 (wire protocol: piggyback on ``additional_kwargs``) and
ADR-0003 (provider scope: MiniMax and DeepSeek only). Each streamed chunk is
inspected by ``enrich_chunk`` from ``reasoning_normalizer.py``; when reasoning
is detected it is promoted into ``chunk.additional_kwargs["reasoning_content"]``
so the existing SSE pipeline (``_serialize_chunk_data``) carries it to the
frontend without protocol changes.

Slice 7 adds the request-payload echo: when sending multi-turn conversations,
providers that run in "thinking mode" sometimes reject assistant messages that
are missing ``reasoning_content`` (some MiniMax / DeepSeek proxies return
HTTP 400). To stay defensive we re-inject ``reasoning_content`` into the
outgoing ``messages[role="assistant"]`` payload mirrors, sourced from the
source ``AIMessage.additional_kwargs.reasoning_content``.

Whether this echo is strictly required depends on the upstream proxy. Deer-flow
patches the same path (``PatchedChatDeepSeek._get_request_payload``); we mirror
the pattern to avoid surprise regressions if the deployed proxy turns out to
be in the strict family. If the proxy tolerates the field, the echo is
harmless duplication because the upstream accepts duplicate keys.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator, Sequence
from typing import Any

from langchain_core.language_models.chat_models import LanguageModelInput
from langchain_core.messages import AIMessage, BaseMessage
from langchain_openai import ChatOpenAI

from app.core.chat.llm.reasoning_normalizer import enrich_chunk


def _restore_reasoning_content_into_payload(
    payload_messages: Sequence[dict[str, Any]],
    original_messages: Sequence[BaseMessage],
) -> None:
    """Echo ``reasoning_content`` from source AIMessages into payload assistant dicts.

    Walks ``payload_messages`` and the source messages list in parallel. When
    length and role ordering match, indexing is direct; otherwise match by
    counting ``assistant`` role occurrences on both sides (deer-flow pattern
    at ``models/patched_deepseek.py:20-40``).

    Mirrors ``reasoning_content`` from the source message into the outgoing
    payload dict as a sibling of ``content`` / ``role`` — never overwriting or
    dropping the existing payload keys. If a payload message already carries
    a ``reasoning_content`` field (e.g. it round-tripped from a prior turn
    and survived), we leave it untouched.
    """

    if len(payload_messages) == len(original_messages):
        for payload_msg, orig_msg in zip(payload_messages, original_messages):
            if payload_msg.get("role") != "assistant" or not isinstance(orig_msg, AIMessage):
                continue
            _echo(orig_msg, payload_msg)
        return

    # Length mismatch — match by counting role occurrences.
    used_indexes: set[int] = set()
    for payload_msg in payload_messages:
        if payload_msg.get("role") != "assistant":
            continue
        ai_index = _match_ai_index(original_messages, used_indexes)
        if ai_index is None:
            continue
        orig_msg = original_messages[ai_index]
        if isinstance(orig_msg, AIMessage):
            _echo(orig_msg, payload_msg)


def _echo(orig_msg: AIMessage, payload_msg: dict[str, Any]) -> None:
    """Copy ``reasoning_content`` from ``orig_msg`` into ``payload_msg`` if absent."""
    if "reasoning_content" in payload_msg:
        return
    reasoning = orig_msg.additional_kwargs.get("reasoning_content")
    if isinstance(reasoning, str) and reasoning:
        payload_msg["reasoning_content"] = reasoning


def _match_ai_index(
    original_messages: Sequence[BaseMessage],
    used: set[int],
) -> int | None:
    """Find the next AIMessage index whose reasoning should map to the next assistant payload."""
    candidates = [
        idx
        for idx, m in enumerate(original_messages)
        if isinstance(m, AIMessage) and idx not in used
    ]
    if not candidates:
        return None
    chosen = candidates[0]
    used.add(chosen)
    return chosen


class PatchedChat(ChatOpenAI):
    """``ChatOpenAI`` that promotes reasoning deltas into ``additional_kwargs``.

    Streaming behavior: each chunk overwrites any previously written
    ``reasoning_content`` with the value extracted from that chunk (or
    appends, for MiniMax's per-chunk partial ``delta.reasoning_details`` —
    see ``enrich_chunk``).

    Request payload behavior: when an assistant message's source carries
    ``additional_kwargs.reasoning_content``, the field is also echoed into
    the outgoing ``messages[].reasoning_content`` slot. Defensive against
    proxies that require the field on every assistant turn in thinking mode.
    """

    def _stream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        **kwargs: object,
    ) -> Iterator[object]:
        for chunk in super()._stream(messages, stop=stop, **kwargs):
            enrich_chunk(chunk)
            yield chunk

    async def _astream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        **kwargs: object,
    ) -> AsyncIterator[object]:
        async for chunk in super()._astream(messages, stop=stop, **kwargs):
            enrich_chunk(chunk)
            yield chunk

    def _get_request_payload(
        self,
        input_: LanguageModelInput,
        *,
        stop: list[str] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Build the OpenAI request payload with ``reasoning_content`` echoed.

        See module docstring (slice 7) for the rationale. Mirrors the
        deer-flow pattern at ``models/patched_deepseek.py:35-59``.
        """
        original_messages = self._convert_input(input_).to_messages()
        payload = super()._get_request_payload(input_, stop=stop, **kwargs)
        payload_messages = payload.get("messages")
        if isinstance(payload_messages, list):
            _restore_reasoning_content_into_payload(payload_messages, original_messages)
        return payload


__all__ = ["PatchedChat"]
