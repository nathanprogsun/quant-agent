"""Shared utilities for jq_kb.

RAG primitives (BM25, RRF fusion) are now provided by LlamaIndex:
- BM25: ``llama_index.retrievers.bm25.BM25Retriever``
- RRF fusion: ``llama_index.core.retrievers.QueryFusionRetriever``

This module is kept as a placeholder for any future jq_kb-specific helpers
(e.g. custom tokenizers, query normalizers, eval scorers).
"""

from __future__ import annotations

from typing import Any


def json_safe_value(value: Any) -> Any:
    """Recursively convert values to JSON-serializable forms (e.g. set → list)."""
    if isinstance(value, set):
        return sorted(json_safe_value(item) for item in value)
    if isinstance(value, (list, tuple)):
        return [json_safe_value(item) for item in value]
    if isinstance(value, dict):
        return {str(k): json_safe_value(v) for k, v in value.items()}
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)
