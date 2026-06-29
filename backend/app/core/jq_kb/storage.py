"""ChromaVectorStore-backed storage for jq_api chunks (LlamaIndex-native).

Uses the canonical LlamaIndex ``IngestionPipeline`` pattern:
- Reader: custom ``JqApiJsonReader`` (our hand-authored records → Document)
- Transformations: ``JqApiChunkToNode`` (Pydantic → TextNode) + embed
- Vector store: ``ChromaVectorStore`` (persistent)

BM25 is kept hand-rolled (LlamaIndex's BM25Retriever needs in-memory nodes,
and we want persistence across processes).

Why IngestionPipeline instead of ``index.insert()``:
- Built-in dedup via ``doc_id`` hashing (skips unchanged nodes on re-ingest)
- Composable: add TitleExtractor/SummaryExtractor/QuestionsAnswered later
- Cache layer (Redis/SQLite) optional for production
"""

from __future__ import annotations

import json
import logging
import pickle
from collections.abc import Sequence
from datetime import date
from pathlib import Path
from typing import Any

import chromadb
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

from app.core.jq_kb.chunkers.jq_api import chunk_jq_api_records
from app.core.jq_kb.embeddings import get_embedding_model
from app.core.jq_kb.paths import (
    JQ_API_BM25_PATH,
    JQ_API_CHROMA_PATH,
    JQ_API_COLLECTION_NAME,
    JQ_API_MANIFEST_PATH,
    JQ_API_RAW_DIR,
    PILOT_FUNCTIONS,
)
from app.core.jq_kb.schemas import JqApiChunk, Library, LibraryManifest, env_support_flags

logger = logging.getLogger(__name__)


class JqApiJsonReader(BaseReader):  # type: ignore[misc]  # BaseReader typed as Any (stub missing)
    """LlamaIndex-compatible reader for our pilot.json / full.json shape.

    Output: one ``Document`` per raw record, with all metadata pre-populated.
    Downstream ``JqApiChunkToNode`` converts these into TextNodes.
    """

    def __init__(self, raw_dir: Path = JQ_API_RAW_DIR) -> None:
        self.raw_dir = raw_dir

    def load_data(self, *, pilot_only: bool = False) -> list[Document]:
        """Load all *.json under ``raw_dir`` → list[Document].

        Each record becomes a Document with metadata mirroring the record
        fields, so the chunker transform can rebuild a JqApiChunk losslessly.
        """
        files: list[Path] = []
        pilot_path = self.raw_dir / "pilot.json"
        if pilot_only:
            if not pilot_path.is_file():
                raise FileNotFoundError(pilot_path)
            files = [pilot_path]
        else:
            files = sorted(self.raw_dir.glob("*.json"))
            if not files:
                raise FileNotFoundError(f"No raw JSON under {self.raw_dir}")

        records: list[dict[str, Any]] = []
        for path in files:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and "functions" in data:
                records.extend(data["functions"])
            elif isinstance(data, list):
                records.extend(data)
            else:
                raise ValueError(f"Unexpected shape in {path}")

        if pilot_only:
            allowed = set(PILOT_FUNCTIONS)
            records = [r for r in records if r.get("function_name") in allowed]

        chunks = chunk_jq_api_records(records)
        return chunks_to_documents(chunks)


class JqApiChunkToNode(TransformComponent):  # type: ignore[misc]  # BaseReader typed as Any (stub missing)
    """IngestionPipeline transformation: Document → TextNode with stable id.

    LlamaIndex's default Document → TextNode just uses text + metadata, but
    we need explicit node ids so re-ingests dedupe correctly.
    """

    def __call__(self, nodes: Sequence[Document], **kwargs: Any) -> list[TextNode]:
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


def chunk_to_document(chunk: JqApiChunk) -> Document:
    """Convert one ``JqApiChunk`` → LlamaIndex ``Document`` for ingestion."""
    return Document(
        doc_id=chunk.id,
        text=chunk.contextual_content,
        metadata={
            "function_name": chunk.function_name,
            "module": chunk.module,
            "signature": chunk.signature,
            "env": ",".join(e.value for e in chunk.env),
            "source_url": chunk.source_url,
            "returns": chunk.returns,
            "description": chunk.content.split("\n")[0].replace("描述: ", ""),
            **env_support_flags(chunk.env),
        },
        excluded_embed_metadata_keys=["source_url"],
        excluded_llm_metadata_keys=["source_url"],
    )


def chunks_to_documents(chunks: list[JqApiChunk]) -> list[Document]:
    return [chunk_to_document(c) for c in chunks]


def build_jq_api_ingestion_pipeline(
    *,
    vector_store: ChromaVectorStore | None = None,
) -> IngestionPipeline:
    """Build the jq_api IngestionPipeline (demo: ``build_pipeline``).

    Transformations vs enterprise demo:
    - **No SentenceSplitter** — each JQ API function is already one atomic chunk.
    - **No Title/Summary/Questions extractors** — structured metadata comes from
      the chunker (function_name, signature, env flags); LLM extraction would
      be slow and redundant for API reference docs.
    - **BGE local embedding** instead of OpenAIEmbedding.
    """
    return IngestionPipeline(
        transformations=[JqApiChunkToNode(), get_embedding_model()],
        vector_store=vector_store,
    )


def create_chroma_vector_store(
    *,
    chroma_path: Path = JQ_API_CHROMA_PATH,
    collection_name: str = JQ_API_COLLECTION_NAME,
) -> ChromaVectorStore:
    """Initialize persistent Chroma collection (demo: chroma setup block)."""
    client = _chroma_client(chroma_path)
    collection = client.get_or_create_collection(
        name=collection_name,
        metadata={"hnsw:space": "cosine"},
    )
    return ChromaVectorStore(chroma_collection=collection)


def _chroma_client(chroma_path: Path) -> chromadb.api.ClientAPI:
    chroma_path.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(chroma_path))


class JqApiStore:
    """Hybrid storage: LlamaIndex VectorStoreIndex (Chroma) + BM25 pickle.

    Public API unchanged so callers (ingest script, retriever, tests) work
    as before.
    """

    def __init__(
        self,
        chroma_path: Path = JQ_API_CHROMA_PATH,
        bm25_path: Path = JQ_API_BM25_PATH,
        collection_name: str = JQ_API_COLLECTION_NAME,
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
        """Load BM25 retriever from pickle (built from raw chunks, not node text)."""
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

    def persist_bm25(self, nodes: list[TextNode], chunks: list[JqApiChunk]) -> None:
        """Write BM25 pickle — LlamaIndex BM25Retriever is in-memory only."""
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
        """Async ingestion via ``IngestionPipeline.arun`` (demo: ``pipeline.arun``)."""
        if not documents:
            return []
        vs = vector_store or self.index._storage_context.vector_store
        pipeline = build_jq_api_ingestion_pipeline(vector_store=vs)
        nodes = await pipeline.arun(documents=documents, num_workers=num_workers)
        return list(nodes)

    def upsert_chunks(self, chunks: list[JqApiChunk]) -> None:
        """Sync ingest wrapper — used by unit tests."""
        if not chunks:
            return
        documents = chunks_to_documents(chunks)
        pipeline = build_jq_api_ingestion_pipeline(
            vector_store=self.index._storage_context.vector_store,
        )
        nodes = pipeline.run(documents=documents)
        self.persist_bm25(nodes, chunks)
        logger.info("Upserted %d jq_api chunks via IngestionPipeline", len(chunks))

    def write_manifest(
        self,
        *,
        chunks_count: int,
        embedding_model: str,
        notes: str = "",
        function_names: list[str] | None = None,
    ) -> None:
        payload = LibraryManifest(
            library=Library.JQ_API,
            version=date.today().isoformat(),
            chunks_count=chunks_count,
            embedding_model=embedding_model,
            notes=notes,
        ).model_dump()
        payload["function_names"] = function_names or []
        JQ_API_MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
        JQ_API_MANIFEST_PATH.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )

    def get_by_function_name(self, function_name: str) -> dict[str, Any] | None:
        """Exact-match shortcut: bypasses RAG, used when user names a function explicitly."""
        filters = MetadataFilters(
            filters=[MetadataFilter(key="function_name", value=function_name)],
            condition=FilterCondition.AND,
        )
        retriever = self.index.as_retriever(
            similarity_top_k=1,
            filters=filters,
        )
        hits = retriever.retrieve("function:" + function_name)
        if not hits:
            return None
        node = hits[0].node
        return {
            "id": node.node_id,
            "document": node.text,
            "metadata": dict(node.metadata),
        }

    def vector_search(self, query: str, *, top_k: int = 10) -> list[tuple[str, float]]:
        """Vector-only ranked list — kept for any callers wanting raw cosine scores."""
        retriever = self.index.as_retriever(similarity_top_k=top_k)
        hits = retriever.retrieve(query)
        return [(h.node.node_id, float(h.score or 0.0)) for h in hits]
