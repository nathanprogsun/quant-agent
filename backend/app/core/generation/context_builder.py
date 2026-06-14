"""Format DC42 retrieval results for agent prompt injection."""

from __future__ import annotations

import logging

from app.core.dc42.retriever import DC42Retriever
from app.core.dc42.types import RetrievalResult

logger = logging.getLogger(__name__)

DEFAULT_TOP_K = 5


def format_dc42_context(
    result: RetrievalResult,
    *,
    max_chunks: int = DEFAULT_TOP_K,
) -> str:
    """Render retrieved DC42 chunks as compact reference text for the system prompt."""
    chunks = result.chunks[:max_chunks]
    if not chunks:
        return ""

    lines = [
        "以下是与用户问题相关的 DC42 策略知识片段，回答时请优先参考：",
        result.summary,
    ]
    for index, chunk in enumerate(chunks, start=1):
        strategy_hint = chunk.metadata.get("strategy_id") or chunk.strategy_id
        lines.append(
            f"[{index}] ({chunk.chunk_type}, strategy={strategy_hint})\n{chunk.content.strip()}"
        )
    return "\n\n".join(lines)


async def build_dc42_context(
    user_query: str,
    retriever: DC42Retriever,
    *,
    top_k: int = DEFAULT_TOP_K,
) -> str:
    """Retrieve DC42 chunks for a user query and format them for prompt injection."""
    if not user_query.strip():
        return ""

    try:
        result = await retriever.retrieve_by_intent(user_query.strip())
    except Exception:
        logger.exception("DC42 retrieval failed for query: %s", user_query[:80])
        return ""

    return format_dc42_context(result, max_chunks=top_k)
