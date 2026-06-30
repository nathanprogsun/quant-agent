"""Memory block builder + token counter for injection (P4.2 / L1).

Builds the ``<memory>`` block injected by DynamicContextMiddleware as
``HumanMessage(id='{stable_id}__memory')``. The block is token-budgeted against
``MemoryConfig.max_injection_tokens`` using the configured counter
(``tiktoken`` default).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from app.config.memory_config import MemoryConfig


class _HasContent(Protocol):
    content: str


class _HasMemory(_HasContent, Protocol):
    confidence: float
    source: str | None


_TIKTOKEN_ENCODER: Any | None = None


def _get_encoder() -> Any:
    global _TIKTOKEN_ENCODER
    if _TIKTOKEN_ENCODER is None:
        import tiktoken  # noqa: PLC0415 — lazy: heavy import, only needed for tiktoken counting

        _TIKTOKEN_ENCODER = tiktoken.get_encoding("cl100k_base")
    return _TIKTOKEN_ENCODER


def count_tokens(text: str, method: str) -> int:
    """Return the token count of ``text`` per ``method``."""
    if not text:
        return 0
    if method == "tiktoken":
        try:
            return len(_get_encoder().encode(text))
        except Exception:
            return max(1, len(text) // 4)
    # 'none' or unknown — character heuristic.
    return max(1, len(text) // 4)


def _format_sections(memories: Sequence[_HasMemory], facts: Sequence[_HasContent]) -> str:
    sections: list[str] = []
    if memories:
        sections.append("[User Memories]")
        for mem in memories:
            confidence_str = f" (confidence: {mem.confidence:.0%})" if mem.confidence < 1.0 else ""
            source_str = f" [source: {mem.source}]" if mem.source else ""
            sections.append(f"- {mem.content}{confidence_str}{source_str}")
    if facts:
        sections.append("[User Facts]")
        for fact in facts:
            sections.append(f"- {fact.content}")
    return "\n".join(sections)


def build_memory_block(
    memories: Sequence[_HasMemory],
    facts: Sequence[_HasContent],
    config: MemoryConfig,
) -> str | None:
    """Build a token-budgeted ``<memory>`` block, or None when empty.

    Drops the last fact, then the last memory, until the block fits
    ``max_injection_tokens``.
    """
    body = _format_sections(memories, facts)
    if not body:
        return None
    block = f"<memory>\n{body}\n</memory>"

    mem_list = list(memories)
    fact_list = list(facts)
    while count_tokens(block, config.token_counting) > config.max_injection_tokens and (
        mem_list or fact_list
    ):
        if fact_list:
            fact_list.pop()
        elif mem_list:
            mem_list.pop()
        body = _format_sections(mem_list, fact_list)
        block = f"<memory>\n{body}\n</memory>"
    return block


__all__ = ["build_memory_block", "count_tokens"]
