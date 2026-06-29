"""Full-corpus jq_kb ingestion (jq_api / jq_dict / jq_strategy)."""

from __future__ import annotations

import asyncio
import logging
import shutil
from collections import Counter
from pathlib import Path

from llama_index.core.schema import Document, TextNode

from app.core.jq_kb.cli_logging import flush_inference_progress, reset_inference_progress
from app.core.jq_kb.dict_storage import (
    JqDictJsonReader,
    JqDictStore,
    build_jq_dict_ingestion_pipeline,
    create_jq_dict_chroma_vector_store,
)
from app.core.jq_kb.embeddings import default_embedding_model_name, warm_up_models
from app.core.jq_kb.paths import (
    JQ_API_BM25_PATH,
    JQ_API_CHROMA_PATH,
    JQ_DICT_BM25_PATH,
    JQ_DICT_CHROMA_PATH,
    JQ_STRATEGY_BM25_PATH,
    JQ_STRATEGY_CHROMA_PATH,
)
from app.core.jq_kb.query_rewriter import reset_known_names_cache
from app.core.jq_kb.schemas import DictType, JqApiChunk, JqDictChunk, JqStrategyChunk, StrategyLayer
from app.core.jq_kb.storage import (
    JqApiJsonReader,
    JqApiStore,
    build_jq_api_ingestion_pipeline,
    create_chroma_vector_store,
)
from app.core.jq_kb.strategy_storage import (
    JqStrategyJsonReader,
    JqStrategyStore,
    build_jq_strategy_ingestion_pipeline,
    create_jq_strategy_chroma_vector_store,
)

logger = logging.getLogger(__name__)

CHROMA_INGEST_BATCH_SIZE = 500


def _dedupe_documents(documents: list[Document]) -> list[Document]:
    seen: set[str] = set()
    out: list[Document] = []
    for doc in documents:
        doc_id = doc.doc_id or doc.id_
        if doc_id not in seen:
            seen.add(doc_id)
            out.append(doc)
    return out


def _clear_paths(*paths: Path) -> None:
    for p in paths:
        if p.is_dir():
            shutil.rmtree(p)
        elif p.is_file():
            p.unlink()


async def ingest_jq_api(*, reset: bool = False) -> int:
    reset_inference_progress("jq_api")
    if reset:
        _clear_paths(JQ_API_CHROMA_PATH, JQ_API_BM25_PATH)
        logger.info("Cleared jq_api chroma_db/ and bm25.pkl")

    reader = JqApiJsonReader()
    documents = _dedupe_documents(reader.load_data())
    logger.info("jq_api: embedding %d documents", len(documents))
    vector_store = create_chroma_vector_store()
    pipeline = build_jq_api_ingestion_pipeline(vector_store=vector_store)
    nodes: list[TextNode] = list(await pipeline.arun(documents=documents, num_workers=1))

    store = JqApiStore()
    store.persist_bm25(nodes, _jq_api_chunks_from_documents(documents))
    store.write_manifest(
        chunks_count=len(nodes),
        embedding_model=default_embedding_model_name(),
        notes="full ingest",
        function_names=sorted({str(d.metadata.get("function_name", "")) for d in documents} - {""}),
    )
    reset_known_names_cache()
    flush_inference_progress()
    logger.info("jq_api ingest complete: %d nodes", len(nodes))
    return len(nodes)


async def ingest_jq_dict(*, reset: bool = False) -> int:
    reset_inference_progress("jq_dict")
    if reset:
        _clear_paths(JQ_DICT_CHROMA_PATH, JQ_DICT_BM25_PATH)
        logger.info("Cleared jq_dict chroma_db/ and bm25.pkl")

    reader = JqDictJsonReader()
    documents = _dedupe_documents(reader.load_data())
    logger.info("jq_dict: embedding %d documents in batches of %d", len(documents), CHROMA_INGEST_BATCH_SIZE)
    vector_store = create_jq_dict_chroma_vector_store()
    pipeline = build_jq_dict_ingestion_pipeline(vector_store=vector_store)
    nodes: list[TextNode] = []
    for start in range(0, len(documents), CHROMA_INGEST_BATCH_SIZE):
        batch = documents[start : start + CHROMA_INGEST_BATCH_SIZE]
        nodes.extend(pipeline.run(documents=batch))
        logger.info(
            "jq_dict batch %d-%d / %d documents → %d nodes so far",
            start + 1,
            start + len(batch),
            len(documents),
            len(nodes),
        )

    store = JqDictStore()
    store.persist_bm25(nodes, _jq_dict_chunks_from_documents(documents))
    store.write_manifest(
        chunks_count=len(nodes),
        embedding_model=default_embedding_model_name(),
        notes="full ingest",
        codes=sorted({str(d.metadata.get("code", "")) for d in documents} - {""}),
    )
    reset_known_names_cache()
    flush_inference_progress()
    logger.info("jq_dict ingest complete: %d nodes", len(nodes))
    return len(nodes)


async def ingest_jq_strategy(*, reset: bool = False) -> int:
    reset_inference_progress("jq_strategy")
    if reset:
        _clear_paths(JQ_STRATEGY_CHROMA_PATH, JQ_STRATEGY_BM25_PATH)
        logger.info("Cleared jq_strategy chroma_db/ and bm25.pkl")

    reader = JqStrategyJsonReader()
    documents = reader.load_data()
    logger.info("jq_strategy: embedding %d documents in batches of %d", len(documents), CHROMA_INGEST_BATCH_SIZE)
    vector_store = create_jq_strategy_chroma_vector_store()
    pipeline = build_jq_strategy_ingestion_pipeline(vector_store=vector_store)
    nodes: list[TextNode] = []
    for start in range(0, len(documents), CHROMA_INGEST_BATCH_SIZE):
        batch = documents[start : start + CHROMA_INGEST_BATCH_SIZE]
        nodes.extend(pipeline.run(documents=batch))
        logger.info(
            "jq_strategy batch %d-%d / %d documents → %d nodes so far",
            start + 1,
            start + len(batch),
            len(documents),
            len(nodes),
        )

    store = JqStrategyStore()
    chunks = _jq_strategy_chunks_from_documents(documents)
    store.persist_bm25(nodes, chunks)
    store.write_manifest(
        chunks_count=len(nodes),
        embedding_model=default_embedding_model_name(),
        notes="full ingest",
        post_ids=sorted({c.post_id for c in chunks}),
        by_layer=dict(Counter(c.layer.value for c in chunks)),
    )
    reset_known_names_cache()
    flush_inference_progress()
    logger.info("jq_strategy ingest complete: %d nodes", len(nodes))
    return len(nodes)


async def ingest_all(*, reset: bool = False, only: str | None = None) -> dict[str, int]:
    warm_up_models()
    runners = {
        "jq_api": ingest_jq_api,
        "jq_dict": ingest_jq_dict,
        "jq_strategy": ingest_jq_strategy,
    }
    if only:
        if only not in runners:
            raise ValueError(f"unknown library {only!r}; choose from {sorted(runners)}")
        return {only: await runners[only](reset=reset)}
    return {name: await fn(reset=reset) for name, fn in runners.items()}


def _jq_api_chunks_from_documents(documents: list[Document]) -> list[JqApiChunk]:
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


def _jq_dict_chunks_from_documents(documents: list[Document]) -> list[JqDictChunk]:
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


def _jq_strategy_chunks_from_documents(documents: list[Document]) -> list[JqStrategyChunk]:
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


def run_ingest_all(*, reset: bool = False, only: str | None = None) -> dict[str, int]:
    return asyncio.run(ingest_all(reset=reset, only=only))
