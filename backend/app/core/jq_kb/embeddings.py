"""LlamaIndex-backed embedding + cross-encoder reranker (local HF models).

Provides lazy singletons for:
- HuggingFaceEmbedding (BAAI/bge-large-zh-v1.5)
- SentenceTransformerRerank (BAAI/bge-reranker-large)

Both models must already exist locally under ``backend/data/models/BAAI/``
(downloaded via ``hf download <model_id> --local-dir ...``).
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache

from llama_index.core.postprocessor import SentenceTransformerRerank
from llama_index.embeddings.huggingface import HuggingFaceEmbedding

from app.core.jq_kb.paths import (
    DEFAULT_EMBEDDING_MODEL_ID,
    DEFAULT_RERANK_MODEL_ID,
    is_local_model_ready,
    local_model_path,
)

logger = logging.getLogger(__name__)

DEFAULT_EMBEDDING_MODEL = DEFAULT_EMBEDDING_MODEL_ID
DEFAULT_RERANK_MODEL = DEFAULT_RERANK_MODEL_ID

_HF_DOWNLOAD_HINT = (
    "Run: hf download BAAI/bge-large-zh-v1.5 --local-dir backend/data/models/BAAI/bge-large-zh-v1.5 "
    "&& hf download BAAI/bge-reranker-large --local-dir backend/data/models/BAAI/bge-reranker-large"
)


def _resolve_model_path(model_id: str) -> str:
    """Resolve ``hf download --local-dir`` path or raise with instructions."""
    override = os.environ.get("JQ_KB_MODEL_PATH")
    if override:
        return override

    local = local_model_path(model_id)
    if is_local_model_ready(local):
        return str(local)

    raise FileNotFoundError(
        f"Model not found at {local}. {_HF_DOWNLOAD_HINT}"
    )


@lru_cache(maxsize=1)
def get_embedding_model() -> HuggingFaceEmbedding:
    """Lazy singleton: BGE Chinese embedding via LlamaIndex."""
    model_id = os.environ.get("JQ_KB_EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL_ID)
    model_path = _resolve_model_path(model_id)
    logger.info("Loading embedding model from %s", model_path)
    return HuggingFaceEmbedding(
        model_name=model_path,
        embed_batch_size=8,
        normalize=True,
    )


@lru_cache(maxsize=1)
def get_reranker(top_n: int = 5) -> SentenceTransformerRerank | None:
    """Lazy singleton: BGE cross-encoder reranker via LlamaIndex."""
    model_id = os.environ.get("JQ_KB_RERANK_MODEL", DEFAULT_RERANK_MODEL_ID)
    local = local_model_path(model_id)
    if not is_local_model_ready(local):
        logger.warning(
            "Reranker not found at %s — retrieval will skip reranking step. %s",
            local,
            _HF_DOWNLOAD_HINT,
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
