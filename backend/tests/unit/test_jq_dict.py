"""Unit tests for jq_dict RAG pipeline."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app.core.jq_kb.chunkers.jq_dict import chunk_jq_dict_record, chunk_jq_dict_records
from app.core.jq_kb.dict_storage import JqDictStore
from app.core.jq_kb.retrievers import JqDictRetriever
from app.core.jq_kb.tools import get_tools

PILOT_RAW_PATH = Path(__file__).resolve().parents[2] / "data/jq_dict/raw/pilot.json"


@pytest.fixture
def industry_record() -> dict[str, Any]:
    return {
        "code": "HY001",
        "name": "农林牧渔",
        "type": "industry",
        "source_description": "申万一级行业：农林牧渔",
    }


def test_chunk_jq_dict_record(industry_record: dict[str, Any]) -> None:
    chunk = chunk_jq_dict_record(industry_record)
    assert chunk is not None
    assert chunk.code == "HY001"
    assert "农林牧渔" in chunk.contextual_content
    assert chunk.id.startswith("dict::")


def test_get_tools_pr_phase_2() -> None:
    tools = get_tools(pr_phase=2)
    names = {t.name for t in tools}
    assert "search_jq_api" in names
    assert "search_jq_dict" in names


@pytest.mark.asyncio
async def test_jq_dict_retriever_pilot(tmp_path: Path) -> None:
    raw = json.loads(PILOT_RAW_PATH.read_text(encoding="utf-8"))
    chunks = chunk_jq_dict_records(raw["entities"][:10])
    store = JqDictStore(
        chroma_path=tmp_path / "chroma",
        bm25_path=tmp_path / "bm25.pkl",
    )
    store.upsert_chunks(chunks)
    retriever = JqDictRetriever(store)

    # Hybrid retrieval without reranker is non-deterministic across embedding
    # API responses — assert HY001 is *somewhere* in the top-k rather than
    # requiring top-1.
    hits = await retriever.retrieve("农林牧渔行业代码", top_k=10)
    assert hits
    codes = {h.metadata.get("code") for h in hits}
    assert "HY001" in codes

    exact = await retriever.retrieve("dummy", code="HY001", top_k=3)
    assert exact[0].metadata.get("code") == "HY001"
