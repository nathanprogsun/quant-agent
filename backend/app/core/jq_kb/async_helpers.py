"""Offload sync jq_kb I/O and CPU work from the asyncio event loop."""

from __future__ import annotations

from typing import Any

from llama_index.core import QueryBundle
from llama_index.core.postprocessor import SentenceTransformerRerank

from app.util.asyncio_util.adapter import run_in_pool


async def rerank_nodes_async(
    reranker: SentenceTransformerRerank,
    nodes: list[Any],
    query_bundle: QueryBundle,
) -> list[Any]:
    """Run cross-encoder reranking in a worker thread."""
    return await run_in_pool(
        reranker.postprocess_nodes,
        None,
        nodes,
        query_bundle=query_bundle,
    )
