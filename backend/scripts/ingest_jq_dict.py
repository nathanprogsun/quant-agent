"""Ingest jq_dict raw JSON into ChromaDB + BM25."""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import shutil
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from llama_index.core.schema import Document, TextNode
from llama_index.vector_stores.chroma import ChromaVectorStore

from app.core.jq_kb.dict_storage import (
    JqDictJsonReader,
    JqDictStore,
    build_jq_dict_ingestion_pipeline,
    create_jq_dict_chroma_vector_store,
)
from app.core.jq_kb.embeddings import DEFAULT_EMBEDDING_MODEL, warm_up_models
from app.core.jq_kb.paths import JQ_DICT_BM25_PATH, JQ_DICT_CHROMA_PATH
from app.core.jq_kb.query_rewriter import reset_known_names_cache
from app.core.jq_kb.schemas import DictType, JqDictChunk

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Chroma default max batch size is 5461; stay below for embedding + metadata overhead.
CHROMA_INGEST_BATCH_SIZE = 4000


def load_documents(*, pilot: bool) -> list[Document]:
    reader = JqDictJsonReader()
    documents = reader.load_data(pilot_only=pilot)
    logger.info("Loaded %d jq_dict documents", len(documents))
    return documents


def dedupe_documents(documents: list[Document]) -> list[Document]:
    seen: set[str] = set()
    out: list[Document] = []
    for doc in documents:
        doc_id = doc.doc_id or doc.id_
        if doc_id not in seen:
            seen.add(doc_id)
            out.append(doc)
    return out


async def run_ingestion_pipeline(
    *,
    pilot: bool,
    reset: bool,
    num_workers: int = 1,
) -> tuple[list[TextNode], list[Document]]:
    if reset:
        for p in (JQ_DICT_CHROMA_PATH, JQ_DICT_BM25_PATH):
            if p.is_dir():
                shutil.rmtree(p)
            elif p.is_file():
                p.unlink()
        logger.info("Cleared jq_dict chroma_db/ and bm25.pkl")

    warm_up_models()
    documents = dedupe_documents(load_documents(pilot=pilot))
    vector_store = create_jq_dict_chroma_vector_store()
    pipeline = build_jq_dict_ingestion_pipeline(vector_store=vector_store)
    logger.info(
        "Running ingestion pipeline (sync, batch_size=%d)...",
        CHROMA_INGEST_BATCH_SIZE,
    )
    nodes: list[TextNode] = []
    for start in range(0, len(documents), CHROMA_INGEST_BATCH_SIZE):
        batch = documents[start : start + CHROMA_INGEST_BATCH_SIZE]
        nodes.extend(pipeline.run(documents=batch))
        logger.info(
            "Ingested batch %d-%d / %d",
            start + 1,
            start + len(batch),
            len(documents),
        )
    logger.info("Ingested %d jq_dict nodes", len(nodes))

    store = JqDictStore()
    chunks = _documents_as_chunks(documents)
    store.persist_bm25(nodes, chunks)
    model = os.environ.get("JQ_KB_EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL)
    store.write_manifest(
        chunks_count=len(nodes),
        embedding_model=model,
        notes="pilot ingest" if pilot else "full ingest",
        codes=sorted({str(d.metadata.get("code", "")) for d in documents} - {""}),
    )
    reset_known_names_cache()
    return nodes, documents


def _documents_as_chunks(documents: list[Document]) -> list[JqDictChunk]:
    stubs: list[JqDictChunk] = []
    for doc in documents:
        meta = doc.metadata or {}
        stubs.append(
            JqDictChunk(
                id=doc.doc_id or doc.id_,
                code=str(meta.get("code", "")),
                name=str(meta.get("name", "")),
                dict_type=DictType(str(meta.get("dict_type", "field"))),
                content=doc.text,
                contextual_content=doc.text,
            )
        )
    return stubs


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest jq_dict chunks")
    parser.add_argument("--pilot", action="store_true")
    parser.add_argument("--reset", action="store_true")
    parser.add_argument("--num-workers", type=int, default=1)
    args = parser.parse_args()
    asyncio.run(
        run_ingestion_pipeline(
            pilot=args.pilot,
            reset=args.reset,
            num_workers=args.num_workers,
        )
    )


if __name__ == "__main__":
    main()
