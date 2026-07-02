"""ChromaVectorStore-backed storage for jq_strategy chunks."""

from __future__ import annotations

import json
import logging
import pickle
from collections.abc import Sequence
from datetime import date
from pathlib import Path
from typing import Any

from llama_index.core import VectorStoreIndex
from llama_index.core.ingestion import IngestionPipeline
from llama_index.core.readers.base import BaseReader
from llama_index.core.schema import Document, TextNode, TransformComponent
from llama_index.core.vector_stores import (
    FilterCondition,
    MetadataFilter,
    MetadataFilters,
)
from llama_index.retrievers.bm25 import BM25Retriever
from llama_index.vector_stores.chroma import ChromaVectorStore

from app.core.jq_kb.chunkers.jq_strategy import chunk_jq_strategy_posts
from app.core.jq_kb.embeddings import get_embedding_model
from app.core.jq_kb.paths import (
    JQ_STRATEGY_BM25_PATH,
    JQ_STRATEGY_CHROMA_PATH,
    JQ_STRATEGY_COLLECTION_NAME,
    JQ_STRATEGY_MANIFEST_PATH,
    JQ_STRATEGY_RAW_DIR,
    JQ_STRATEGY_SUMMARIES_PATH,
)
from app.core.jq_kb.schemas import JqStrategyChunk, Library, LibraryManifest
from app.core.jq_kb.storage import _chroma_client, create_chroma_vector_store

logger = logging.getLogger(__name__)


def _load_summaries_map(path: Path = JQ_STRATEGY_SUMMARIES_PATH) -> dict[int, dict[str, Any]]:
    if not path.is_file():
        return {}
    out: dict[int, dict[str, Any]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        out[int(row["post_id"])] = row
    return out


class JqStrategyJsonReader(BaseReader):
    """Reader for jq_strategy pilot.json / posts.json."""

    def __init__(self, raw_dir: Path = JQ_STRATEGY_RAW_DIR) -> None:
        self.raw_dir = raw_dir

    def load_data(self, *, pilot_only: bool = False) -> list[Document]:
        if pilot_only:
            path = self.raw_dir / "pilot.json"
        else:
            path = self.raw_dir / "posts.json"
            if not path.is_file():
                path = self.raw_dir / "pilot.json"
        if not path.is_file():
            raise FileNotFoundError(path)

        data = json.loads(path.read_text(encoding="utf-8"))
        posts = data.get("posts", data if isinstance(data, list) else [])
        summaries = _load_summaries_map()
        merged: list[dict[str, Any]] = []
        for post in posts:
            pid = int(post["post_id"])
            if pid in summaries and "summary" not in post:
                post = {**post, "summary": summaries[pid]}
            merged.append(post)

        logger.info("Reading %d posts from %s", len(merged), path.name)
        chunks = chunk_jq_strategy_posts(merged)

        # Dedupe by chunk id (Chroma requires unique node ids per batch).
        seen: set[str] = set()
        deduped: list[JqStrategyChunk] = []
        for c in chunks:
            if c.id in seen:
                logger.warning("Dropping duplicate chunk id: %s", c.id)
                continue
            seen.add(c.id)
            deduped.append(c)
        if len(deduped) != len(chunks):
            logger.info(
                "Deduped %d → %d unique chunks (post_id collisions)",
                len(chunks),
                len(deduped),
            )
        return strategy_chunks_to_documents(deduped)


class JqStrategyChunkToNode(TransformComponent):
    def __call__(self, nodes: Sequence[Document], **kwargs: Any) -> list[TextNode]:  # type: ignore[override]
        return [
            TextNode(
                id_=doc.doc_id or doc.id_,
                text=doc.text,
                metadata=dict(doc.metadata or {}),
                excluded_embed_metadata_keys=list(doc.excluded_embed_metadata_keys or []),
                excluded_llm_metadata_keys=list(doc.excluded_llm_metadata_keys or []),
            )
            for doc in nodes
        ]


def strategy_chunk_to_document(chunk: JqStrategyChunk) -> Document:
    return Document(
        doc_id=chunk.id,
        text=chunk.contextual_content,
        metadata=chunk.to_metadata(),
        excluded_embed_metadata_keys=["source_url"],
        excluded_llm_metadata_keys=["source_url"],
    )


def strategy_chunks_to_documents(chunks: list[JqStrategyChunk]) -> list[Document]:
    return [strategy_chunk_to_document(c) for c in chunks]


def build_jq_strategy_ingestion_pipeline(
    *,
    vector_store: ChromaVectorStore | None = None,
) -> IngestionPipeline:
    return IngestionPipeline(
        transformations=[JqStrategyChunkToNode(), get_embedding_model()],
        vector_store=vector_store,
    )


def create_jq_strategy_chroma_vector_store() -> ChromaVectorStore:
    return create_chroma_vector_store(
        chroma_path=JQ_STRATEGY_CHROMA_PATH,
        collection_name=JQ_STRATEGY_COLLECTION_NAME,
    )


class JqStrategyStore:
    """Hybrid storage: Chroma vector index + BM25 pickle for jq_strategy."""

    def __init__(
        self,
        chroma_path: Path = JQ_STRATEGY_CHROMA_PATH,
        bm25_path: Path = JQ_STRATEGY_BM25_PATH,
        collection_name: str = JQ_STRATEGY_COLLECTION_NAME,
    ) -> None:
        self.chroma_path = chroma_path
        self.bm25_path = bm25_path
        self.collection_name = collection_name
        self._index: VectorStoreIndex | None = None
        self._bm25: BM25Retriever | None = None

    @property
    def index(self) -> VectorStoreIndex:
        if self._index is None:
            client = _chroma_client(self.chroma_path)
            collection = client.get_or_create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine"},
            )
            vector_store = ChromaVectorStore(chroma_collection=collection)
            self._index = VectorStoreIndex.from_vector_store(
                vector_store=vector_store,
                embed_model=get_embedding_model(),
            )
        return self._index

    def load_bm25(self) -> BM25Retriever | None:
        if self._bm25 is not None:
            return self._bm25
        if not self.bm25_path.is_file():
            return None
        with open(self.bm25_path, "rb") as f:
            data = pickle.load(f)
        self._bm25 = BM25Retriever.from_defaults(
            nodes=data["nodes"],
            similarity_top_k=10,
            stemmer=None,
        )
        return self._bm25

    def persist_bm25(self, nodes: list[TextNode], chunks: list[JqStrategyChunk]) -> None:
        self.bm25_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.bm25_path, "wb") as f:
            pickle.dump(
                {"chunks": [c.model_dump() for c in chunks], "nodes": nodes},
                f,
            )
        self._bm25 = None

    def upsert_chunks(self, chunks: list[JqStrategyChunk]) -> None:
        if not chunks:
            return
        documents = strategy_chunks_to_documents(chunks)
        pipeline = build_jq_strategy_ingestion_pipeline(
            vector_store=self.index._storage_context.vector_store,  # type: ignore[arg-type]
        )
        nodes = pipeline.run(documents=documents)
        self.persist_bm25(nodes, chunks)  # type: ignore[arg-type]
        logger.info("Upserted %d jq_strategy chunks", len(chunks))

    def write_manifest(
        self,
        *,
        chunks_count: int,
        embedding_model: str,
        notes: str = "",
        post_ids: list[int] | None = None,
        by_layer: dict[str, int] | None = None,
    ) -> None:
        payload = LibraryManifest(
            library=Library.JQ_STRATEGY,
            version=date.today().isoformat(),
            chunks_count=chunks_count,
            embedding_model=embedding_model,
            notes=notes,
        ).model_dump()
        payload["post_ids"] = post_ids or []
        payload["by_layer"] = by_layer or {}
        JQ_STRATEGY_MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
        JQ_STRATEGY_MANIFEST_PATH.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )

    def get_by_post_id(self, post_id: int, *, layer: str = "") -> dict[str, Any] | None:
        filters: list[MetadataFilter] = [MetadataFilter(key="post_id", value=post_id)]
        if layer:
            filters.append(MetadataFilter(key="layer", value=layer))
        retriever = self.index.as_retriever(
            similarity_top_k=1,
            filters=MetadataFilters(filters=filters, condition=FilterCondition.AND),  # type: ignore[arg-type]
        )
        hits = retriever.retrieve(f"post_id:{post_id}")
        if not hits:
            return None
        node = hits[0].node
        return {
            "id": node.node_id,
            "document": node.text,  # type: ignore[attr-defined]
            "metadata": dict(node.metadata),
        }
