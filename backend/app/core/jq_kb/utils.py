"""Shared utilities for jq_kb.

RAG primitives (BM25, RRF fusion) are now provided by LlamaIndex:
- BM25: ``llama_index.retrievers.bm25.BM25Retriever``
- RRF fusion: ``llama_index.core.retrievers.QueryFusionRetriever``

This module is kept as a placeholder for any future jq_kb-specific helpers
(e.g. custom tokenizers, query normalizers, eval scorers).
"""

from __future__ import annotations
