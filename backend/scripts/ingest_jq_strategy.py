"""Ingest jq_strategy raw JSON into ChromaDB + BM25."""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import shutil
import sys
from collections import Counter
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from llama_index.core.schema import Document, TextNode

from app.core.jq_kb.embeddings import DEFAULT_EMBEDDING_MODEL, warm_up_models
from app.core.jq_kb.paths import JQ_STRATEGY_BM25_PATH, JQ_STRATEGY_CHROMA_PATH
from app.core.jq_kb.query_rewriter import reset_known_names_cache
from app.core.jq_kb.schemas import JqStrategyChunk, StrategyLayer
from app.core.jq_kb.strategy_storage import (
    JqStrategyJsonReader,
    JqStrategyStore,
    build_jq_strategy_ingestion_pipeline,
    create_jq_strategy_chroma_vector_store,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

CHROMA_INGEST_BATCH_SIZE = 4000


def load_documents(*, pilot: bool) -> list[Document]:
    reader = JqStrategyJsonReader()
    documents = reader.load_data(pilot_only=pilot)
    logger.info("Loaded %d jq_strategy documents", len(documents))
    return documents


async def run_ingestion_pipeline(*, pilot: bool, reset: bool) -> None:
    if reset:
        for p in (JQ_STRATEGY_CHROMA_PATH, JQ_STRATEGY_BM25_PATH):
            if p.is_dir():
                shutil.rmtree(p)
            elif p.is_file():
                p.unlink()
        logger.info("Cleared jq_strategy chroma_db/ and bm25.pkl")

    warm_up_models()
    logger.info("Loading and chunking jq_strategy raw JSON (may take 1-2 min for full corpus)...")
    documents = load_documents(pilot=pilot)
    vector_store = create_jq_strategy_chroma_vector_store()
    pipeline = build_jq_strategy_ingestion_pipeline(vector_store=vector_store)
    nodes: list[TextNode] = []
    for start in range(0, len(documents), CHROMA_INGEST_BATCH_SIZE):
        batch = documents[start : start + CHROMA_INGEST_BATCH_SIZE]
        nodes.extend(pipeline.run(documents=batch))
        logger.info("Ingested batch %d-%d / %d", start + 1, start + len(batch), len(documents))

    store = JqStrategyStore()
    chunks = _documents_as_chunks(documents)
    store.persist_bm25(nodes, chunks)
    by_layer = dict(Counter(c.layer.value for c in chunks))
    post_ids = sorted({c.post_id for c in chunks})
    model = os.environ.get("JQ_KB_EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL)
    store.write_manifest(
        chunks_count=len(nodes),
        embedding_model=model,
        notes="pilot ingest" if pilot else "full ingest",
        post_ids=post_ids,
        by_layer=by_layer,
    )
    reset_known_names_cache()
    logger.info("Ingested %d jq_strategy nodes (%s)", len(nodes), by_layer)


def _documents_as_chunks(documents: list[Document]) -> list[JqStrategyChunk]:
    stubs: list[JqStrategyChunk] = []
    for doc in documents:
        meta = doc.metadata or {}
        stubs.append(
            JqStrategyChunk(
                id=doc.doc_id or doc.id_,
                post_id=int(meta.get("post_id", 0)),
                year=int(meta.get("year", 2023)),
                title=str(meta.get("title", "")),
                author=str(meta.get("author", "unknown")),
                source_url=str(meta.get("source_url", "")),
                layer=StrategyLayer(str(meta.get("layer", "summary"))),
                entity_type=str(meta.get("entity_type", "")),
                entity_name=str(meta.get("entity_name", "")),
                function_name=str(meta.get("function_name", "")),
                strategy_type=str(meta.get("strategy_type", "")),
                content=doc.text,
                contextual_content=doc.text,
            )
        )
    return stubs


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest jq_strategy chunks")
    parser.add_argument("--pilot", action="store_true")
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args()
    asyncio.run(run_ingestion_pipeline(pilot=args.pilot, reset=args.reset))


if __name__ == "__main__":
    main()
