"""LlamaIndex ``BaseEmbedding`` adapter for jq_kb embedding client."""

from __future__ import annotations

from typing import Any

from llama_index.core.base.embeddings.base import BaseEmbedding
from llama_index.core.bridge.pydantic import PrivateAttr

from app.core.jq_kb.embedding_client import embed_texts
from app.settings import get_settings
from app.util.asyncio_util.adapter import run_in_pool


class EmbeddingModel(BaseEmbedding):
    """Configured text embedding model for jq_kb vector indexes."""

    _model_name: str = PrivateAttr()

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._model_name = get_settings().jq_kb_embedding_model

    @classmethod
    def class_name(cls) -> str:
        return "JqKbEmbeddingModel"

    def _get_query_embedding(self, query: str) -> list[float]:
        return embed_texts([query])[0]

    def _get_text_embedding(self, text: str) -> list[float]:
        return embed_texts([text])[0]

    def _get_text_embeddings(self, texts: list[str]) -> list[list[float]]:
        return embed_texts(texts)

    async def _aget_query_embedding(self, query: str) -> list[float]:
        return await run_in_pool(self._get_query_embedding, None, query)

    async def _aget_text_embedding(self, text: str) -> list[float]:
        return self._get_text_embedding(text)

    async def _aget_text_embeddings(self, texts: list[str]) -> list[list[float]]:
        return self._get_text_embeddings(texts)
