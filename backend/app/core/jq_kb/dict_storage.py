"""ChromaVectorStore-backed storage for jq_dict chunks."""

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

from app.core.jq_kb.chunkers.jq_dict import chunk_jq_dict_records, static_suffix_records
from app.core.jq_kb.embeddings import get_embedding_model
from app.core.jq_kb.paths import (
    JQ_DICT_BM25_PATH,
    JQ_DICT_CHROMA_PATH,
    JQ_DICT_COLLECTION_NAME,
    JQ_DICT_MANIFEST_PATH,
    JQ_DICT_RAW_DIR,
)
from app.core.jq_kb.schemas import JqDictChunk, Library, LibraryManifest
from app.core.jq_kb.storage import _chroma_client, create_chroma_vector_store

logger = logging.getLogger(__name__)


class JqDictJsonReader(BaseReader):
    """Reader for jq_dict pilot.json / jq_dict.json crawl output."""

    def __init__(self, raw_dir: Path = JQ_DICT_RAW_DIR) -> None:
        self.raw_dir = raw_dir

    def load_data(self, *, pilot_only: bool = False) -> list[Document]:
        files: list[Path] = []
        pilot_path = self.raw_dir / "pilot.json"
        if pilot_only:
            if not pilot_path.is_file():
                raise FileNotFoundError(pilot_path)
            files = [pilot_path]
        else:
            full_path = self.raw_dir / "full.json"
            files = [full_path] if full_path.is_file() else sorted(self.raw_dir.glob("*.json"))
            if not files:
                raise FileNotFoundError(f"No raw JSON under {self.raw_dir}")

        records: list[dict[str, Any]] = []
        for path in files:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and "entities" in data:
                records.extend(data["entities"])
            elif isinstance(data, list):
                records.extend(data)
            else:
                raise ValueError(f"Unexpected shape in {path}")

        records = _merge_static_suffixes(records)
        chunks = chunk_jq_dict_records(records)
        return dict_chunks_to_documents(chunks)


def _merge_static_suffixes(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    existing = {str(r.get("code", "")) for r in records}
    out = list(records)
    for suffix in static_suffix_records():
        if suffix["code"] not in existing:
            out.append(dict(suffix))
    return out


class JqDictChunkToNode(TransformComponent):
    def __call__(self, nodes: Sequence[Document], **kwargs: Any) -> list[TextNode]:  # type: ignore[override]
        out: list[TextNode] = []
        for doc in nodes:
            out.append(
                TextNode(
                    id_=doc.doc_id or doc.id_,
                    text=doc.text,
                    metadata=dict(doc.metadata or {}),
                    excluded_embed_metadata_keys=list(doc.excluded_embed_metadata_keys or []),
                    excluded_llm_metadata_keys=list(doc.excluded_llm_metadata_keys or []),
                )
            )
        return out


def dict_chunk_to_document(chunk: JqDictChunk) -> Document:
    return Document(
        doc_id=chunk.id,
        text=chunk.contextual_content,
        metadata=chunk.to_metadata(),
        excluded_embed_metadata_keys=["source_url"],
        excluded_llm_metadata_keys=["source_url"],
    )


def dict_chunks_to_documents(chunks: list[JqDictChunk]) -> list[Document]:
    return [dict_chunk_to_document(c) for c in chunks]


def build_jq_dict_ingestion_pipeline(
    *,
    vector_store: ChromaVectorStore | None = None,
) -> IngestionPipeline:
    return IngestionPipeline(
        transformations=[JqDictChunkToNode(), get_embedding_model()],
        vector_store=vector_store,
    )


def create_jq_dict_chroma_vector_store() -> ChromaVectorStore:
    return create_chroma_vector_store(
        chroma_path=JQ_DICT_CHROMA_PATH,
        collection_name=JQ_DICT_COLLECTION_NAME,
    )


class JqDictStore:
    """Hybrid storage: Chroma vector index + BM25 pickle for jq_dict."""

    def __init__(
        self,
        chroma_path: Path = JQ_DICT_CHROMA_PATH,
        bm25_path: Path = JQ_DICT_BM25_PATH,
        collection_name: str = JQ_DICT_COLLECTION_NAME,
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
        nodes = data["nodes"]
        self._bm25 = BM25Retriever.from_defaults(
            nodes=nodes,
            similarity_top_k=10,
            stemmer=None,
        )
        return self._bm25

    def persist_bm25(self, nodes: list[TextNode], chunks: list[JqDictChunk]) -> None:
        self.bm25_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.bm25_path, "wb") as f:
            pickle.dump(
                {"chunks": [c.model_dump() for c in chunks], "nodes": nodes},
                f,
            )
        self._bm25 = None

    async def arun_ingestion(
        self,
        documents: list[Document],
        *,
        vector_store: ChromaVectorStore | None = None,
        num_workers: int = 4,
    ) -> list[TextNode]:
        if not documents:
            return []
        vs = vector_store or self.index._storage_context.vector_store
        pipeline = build_jq_dict_ingestion_pipeline(vector_store=vs)  # type: ignore[arg-type]
        nodes = await pipeline.arun(documents=documents, num_workers=num_workers)
        return list(nodes)  # type: ignore[arg-type]

    def upsert_chunks(self, chunks: list[JqDictChunk]) -> None:
        if not chunks:
            return
        documents = dict_chunks_to_documents(chunks)
        pipeline = build_jq_dict_ingestion_pipeline(
            vector_store=self.index._storage_context.vector_store,  # type: ignore[arg-type]
        )
        nodes = pipeline.run(documents=documents)
        self.persist_bm25(nodes, chunks)  # type: ignore[arg-type]
        logger.info("Upserted %d jq_dict chunks via IngestionPipeline", len(chunks))

    def write_manifest(
        self,
        *,
        chunks_count: int,
        embedding_model: str,
        notes: str = "",
        codes: list[str] | None = None,
    ) -> None:
        payload = LibraryManifest(
            library=Library.JQ_DICT,
            version=date.today().isoformat(),
            chunks_count=chunks_count,
            embedding_model=embedding_model,
            notes=notes,
        ).model_dump()
        payload["codes"] = codes or []
        JQ_DICT_MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
        JQ_DICT_MANIFEST_PATH.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )

    def get_by_code(self, code: str) -> dict[str, Any] | None:
        filters = MetadataFilters(
            filters=[MetadataFilter(key="code", value=code)],
            condition=FilterCondition.AND,
        )
        retriever = self.index.as_retriever(
            similarity_top_k=1,
            filters=filters,
        )
        hits = retriever.retrieve("code:" + code)
        if not hits:
            return None
        node = hits[0].node
        return {
            "id": node.node_id,
            "document": node.text,  # type: ignore[attr-defined]
            "metadata": dict(node.metadata),
        }
