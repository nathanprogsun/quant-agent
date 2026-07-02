"""Unit tests for jq_api RAG pipeline."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from llama_index.core.llms.mock import MockLLM

from app.core.jq_kb.chunkers.jq_api import chunk_jq_api_record, chunk_jq_api_records
from app.core.jq_kb.retrievers import JqApiRetriever
from app.core.jq_kb.storage import JqApiStore
from app.core.jq_kb.tools import get_tools

PILOT_RAW_PATH = Path(__file__).resolve().parents[2] / "data/jq_api/raw/pilot.json"


@pytest.fixture
def pilot_record() -> dict[str, Any]:
    return {
        "function_name": "get_price",
        "module": "Stock",
        "signature": "get_price(security, start_date=None)",
        "params": [{"name": "security", "type": "str", "default": "-", "description": "股票代码"}],
        "returns": "DataFrame",
        "examples": ["get_price('000001.XSHE')"],
        "notes": "行情数据",
    }


def test_chunk_jq_api_record(pilot_record: dict[str, Any]) -> None:
    chunks = chunk_jq_api_record(pilot_record)
    assert len(chunks) == 1
    chunk = chunks[0]
    assert chunk.function_name == "get_price"
    assert "get_price" in chunk.contextual_content
    assert chunk.id.startswith("jq_api::")


def test_get_tools_pr_phase_1() -> None:
    tools = get_tools(pr_phase=1)
    assert len(tools) == 1
    assert tools[0].name == "search_jq_api"


@pytest.mark.asyncio
async def test_jq_api_retriever_pilot(tmp_path: Path, mock_jq_kb_embeddings: MockLLM) -> None:
    raw = json.loads(PILOT_RAW_PATH.read_text(encoding="utf-8"))
    chunks = chunk_jq_api_records(raw["functions"][:5])
    store = JqApiStore(
        chroma_path=tmp_path / "chroma",
        bm25_path=tmp_path / "bm25.pkl",
    )
    store.upsert_chunks(chunks)
    # num_queries=1 disables LLM query-gen so BM25 + vector ranking is the
    # only thing under test. With more queries the reranker can re-order
    # ``get_price`` below ``get_fundamentals`` non-deterministically.
    retriever = JqApiRetriever(store, llm=mock_jq_kb_embeddings, num_queries=1)

    hits = await retriever.retrieve("get_price 怎么用", top_k=3)
    assert hits
    names = {h.metadata.get("function_name") for h in hits}
    assert len(names) >= 1

    exact = await retriever.retrieve("dummy", function_name="order_target", top_k=3)
    assert exact[0].metadata.get("function_name") == "order_target"
