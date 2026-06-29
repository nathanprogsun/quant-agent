"""LlamaIndex-backed embedding + cross-encoder reranker for jq_kb.

Provider-agnostic: delegates to ``app.core.jq_kb.embedding_model.EmbeddingModel``
which talks to an OpenAI-compatible ``/embeddings`` endpoint
(``JQKB_EMBEDDING_*`` env, with legacy ``OPENAI_EMBEDDING_*`` aliases).

The reranker is a BGE cross-encoder loaded locally from
``backend/data/models/BAAI/bge-reranker-large`` if present.
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache

from llama_index.core.postprocessor import SentenceTransformerRerank
from llama_index.embeddings.huggingface import (
    HuggingFaceEmbedding,  # noqa: F401  (kept for tests / fallback)
)

from app.core.jq_kb.embedding_model import EmbeddingModel
from app.core.jq_kb.paths import (
    DEFAULT_RERANK_MODEL_ID,
    is_local_model_ready,
    local_model_path,
)
from app.settings import get_settings

logger = logging.getLogger(__name__)


def default_embedding_model_name() -> str:
    """Provider model name as configured (used in manifests / logs)."""
    return get_settings().jq_kb_embedding_model


@lru_cache(maxsize=1)
def get_embedding_model() -> EmbeddingModel:
    """Lazy singleton: HTTP embedding via the configured provider."""
    model_name = default_embedding_model_name()
    logger.info("Using HTTP embedding model: %s", model_name)
    return EmbeddingModel()


@lru_cache(maxsize=1)
def get_reranker(top_n: int = 5) -> SentenceTransformerRerank | None:
    """Lazy singleton: BGE cross-encoder reranker via LlamaIndex (local HF)."""
    model_id = os.environ.get("JQ_KB_RERANK_MODEL", DEFAULT_RERANK_MODEL_ID)
    local = local_model_path(model_id)
    if not is_local_model_ready(local):
        logger.warning(
            "Reranker not found at %s — retrieval will skip reranking step. "
            "Run: hf download BAAI/bge-reranker-large --local-dir backend/data/models/BAAI/bge-reranker-large",
            local,
        )
        return None
    logger.info("Loading reranker from %s", str(local))
    return SentenceTransformerRerank(
        model=str(local),
        top_n=top_n,
    )


def warm_up_models() -> None:
    """Eager-load embedding (+ reranker if downloaded)."""
    get_embedding_model()
    get_reranker()

