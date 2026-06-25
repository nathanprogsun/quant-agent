"""Ingest jq_api raw JSON into ChromaDB + BM25 via LlamaIndex IngestionPipeline.

Follows the enterprise ingestion demo structure:
    load documents → init Chroma → build_pipeline → pipeline.arun → persist BM25

Data sources under ``backend/data/jq_api/raw/``:
- ``pilot.json``: 20 hand-authored API records for pipeline validation.
- ``full.json``: Chrome MCP crawl of joinquant.com/help/api/help?name=api

Usage::

    cd backend
    .venv/bin/python scripts/ingest_jq_api.py              # full ingest
    .venv/bin/python scripts/ingest_jq_api.py --pilot      # pilot only
    .venv/bin/python scripts/ingest_jq_api.py --reset       # wipe + rebuild

Transformations vs generic demo
---------------------------------
- **No SentenceSplitter** — each JQ API function is one atomic chunk.
- **No LLM metadata extractors** — chunker already emits function_name,
  signature, env flags; LLM extraction would be slow and redundant.
    - **Local BGE embedding** (``BAAI/bge-large-zh-v1.5``) instead of OpenAI.
- **num_workers=1** by default — local torch models cannot be multiprocess-pickled
  (demo uses OpenAI API embedding which supports ``num_workers=8``).
"""

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

from app.core.jq_kb.embeddings import DEFAULT_EMBEDDING_MODEL, warm_up_models
from app.core.jq_kb.paths import JQ_API_BM25_PATH, JQ_API_CHROMA_PATH
from app.core.jq_kb.query_rewriter import reset_known_names_cache
from app.core.jq_kb.schemas import JqApiChunk
from app.core.jq_kb.storage import (
    JqApiJsonReader,
    JqApiStore,
    build_jq_api_ingestion_pipeline,
    create_chroma_vector_store,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 1. Load documents (demo: SimpleDirectoryReader)
# ---------------------------------------------------------------------------

def load_documents(*, pilot: bool) -> list[Document]:
    """Load raw JSON → LlamaIndex Documents via ``JqApiJsonReader``."""
    reader = JqApiJsonReader()
    documents = reader.load_data(pilot_only=pilot)
    logger.info("Loaded %d documents from raw JSON", len(documents))
    return documents


def dedupe_documents(documents: list[Document]) -> list[Document]:
    """Drop duplicate doc_ids (composite-name splits may collide)."""
    seen: set[str] = set()
    out: list[Document] = []
    for doc in documents:
        doc_id = doc.doc_id or doc.id_
        if doc_id not in seen:
            seen.add(doc_id)
            out.append(doc)
    dropped = len(documents) - len(out)
    if dropped:
        logger.info("Dropped %d duplicate documents", dropped)
    return out


# ---------------------------------------------------------------------------
# 2. Build pipeline (demo: build_pipeline)
# ---------------------------------------------------------------------------

def build_pipeline(vector_store: ChromaVectorStore) -> object:
    """Delegate to shared storage helper."""
    return build_jq_api_ingestion_pipeline(vector_store=vector_store)


# ---------------------------------------------------------------------------
# 3. Async ingestion (demo: run_ingestion_pipeline)
# ---------------------------------------------------------------------------

async def run_ingestion_pipeline(
    *,
    pilot: bool,
    reset: bool,
    num_workers: int = 1,
) -> tuple[list[TextNode], list[Document]]:
    """Full async ingest: load → Chroma → arun → BM25 pickle → manifest."""
    logger.info("=" * 60)
    logger.info("Starting jq_api Ingestion Pipeline")
    logger.info("=" * 60)

    if reset:
        for p in (JQ_API_CHROMA_PATH, JQ_API_BM25_PATH):
            if p.is_dir():
                shutil.rmtree(p)
            elif p.is_file():
                p.unlink()
        logger.info("Cleared existing chroma_db/ and bm25.pkl")

    # a) Warm up local embedding model (BGE)
    warm_up_models()

    # b) Load documents
    documents = dedupe_documents(load_documents(pilot=pilot))

    # c) Initialize Chroma vector store
    logger.info("Initializing Chroma vector store at %s", JQ_API_CHROMA_PATH)
    vector_store = create_chroma_vector_store()

    # d) Build and run pipeline (async parallel embedding)
    pipeline = build_pipeline(vector_store)
    logger.info(
        "Running ingestion pipeline (num_workers=%d)...",
        num_workers,
    )
    nodes: list[TextNode] = list(
        await pipeline.arun(documents=documents, num_workers=num_workers)
    )
    logger.info(
        "Ingestion complete: %d nodes written to Chroma",
        len(nodes),
    )

    # e) Persist BM25 + manifest
    store = JqApiStore()
    # Rebuild chunk list from documents for BM25 pickle metadata
    chunks = _documents_as_chunks(documents)
    store.persist_bm25(nodes, chunks)

    model = os.environ.get("JQ_KB_EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL)
    store.write_manifest(
        chunks_count=len(nodes),
        embedding_model=model,
        notes="pilot ingest" if pilot else "full ingest",
        function_names=sorted(
            {str(d.metadata.get("function_name", "")) for d in documents}
            - {""}
        ),
    )
    reset_known_names_cache()

    logger.info("=" * 60)
    logger.info("Ingestion Pipeline Finished Successfully")
    logger.info("=" * 60)
    return nodes, documents


def _documents_as_chunks(documents: list[Document]) -> list[JqApiChunk]:
    """Minimal JqApiChunk stubs for BM25 pickle (id + function_name)."""
    stubs: list[JqApiChunk] = []
    for doc in documents:
        meta = doc.metadata or {}
        stubs.append(
            JqApiChunk(
                id=doc.doc_id or doc.id_,
                function_name=str(meta.get("function_name", "")),
                signature=str(meta.get("signature", "")),
                source_url=str(meta.get("source_url", "")),
                content=doc.text,
                contextual_content=doc.text,
            )
        )
    return stubs


# ---------------------------------------------------------------------------
# 4. CLI entry (demo: main + asyncio.run)
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest jq_api chunks")
    parser.add_argument(
        "--pilot",
        action="store_true",
        help="Ingest 20-function pilot seed (raw/pilot.json)",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete existing chroma_db/ and bm25.pkl before ingesting",
    )
    parser.add_argument(
        "--num-workers",
        type=int,
        default=1,
        help=(
            "Parallel workers for IngestionPipeline.arun (default: 1). "
            "Keep at 1 for local BGE — torch models cannot be forked across workers."
        ),
    )
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
