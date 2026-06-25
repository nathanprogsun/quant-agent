"""Unit tests for jq_strategy RAG pipeline."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.core.jq_kb.ast_parser import extract_entities, extract_function_code
from app.core.jq_kb.chunkers.jq_strategy import chunk_jq_strategy_post
from app.core.jq_kb.parser.strategy_txt import parse_strategy_txt
from app.core.jq_kb.retrievers import JqStrategyRetriever
from app.core.jq_kb.strategy_storage import JqStrategyStore
from app.core.jq_kb.tools import get_tools

SAMPLE_CODE = '''
def initialize(context):
    set_benchmark('000300.XSHG')
    g.stock_count = 20

def handle_data(context, data):
    order_target('000001.XSHE', 100)
'''

SAMPLE_POST = {
    "post_id": 12345,
    "year": 2024,
    "title": "ETF轮动策略-入门2.0",
    "author": "test",
    "source_url": "https://www.joinquant.com/post/12345",
    "code": SAMPLE_CODE,
}


def test_extract_entities_finds_api_calls() -> None:
    entities = extract_entities(SAMPLE_CODE)
    assert "initialize" in entities["functions"]
    assert "order_target" in entities["factors_called"]


def test_extract_function_code() -> None:
    code = extract_function_code(SAMPLE_CODE, "initialize")
    assert "set_benchmark" in code


def test_chunk_jq_strategy_post_layers() -> None:
    chunks = chunk_jq_strategy_post(SAMPLE_POST)
    layers = {c.layer.value for c in chunks}
    assert "summary" in layers
    assert "entity" in layers
    assert "code" in layers


def test_get_tools_pr_phase_3() -> None:
    tools = get_tools(pr_phase=3)
    names = {t.name for t in tools}
    assert "search_jq_api" in names
    assert "search_jq_dict" in names
    assert "search_jq_strategy" in names


@pytest.mark.asyncio
async def test_jq_strategy_retriever_pilot(tmp_path: Path) -> None:
    from app.core.jq_kb.chunkers.jq_strategy import chunk_jq_strategy_posts

    chunks = chunk_jq_strategy_posts([SAMPLE_POST])
    store = JqStrategyStore(
        chroma_path=tmp_path / "chroma",
        bm25_path=tmp_path / "bm25.pkl",
    )
    store.upsert_chunks(chunks)
    retriever = JqStrategyRetriever(store, llm=None, num_queries=1)

    hits = await retriever.retrieve("ETF轮动", top_k=3)
    assert hits
    assert hits[0].metadata.get("post_id") == 12345


def test_parse_strategy_code_suppresses_syntax_warnings() -> None:
    import warnings

    from app.core.jq_kb.ast_parser import _parse_strategy_code

    code = 'x = "\\*bad\\*"\n'
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", SyntaxWarning)
        tree = _parse_strategy_code(code)
    assert tree is not None
    assert not any(isinstance(w.message, SyntaxWarning) for w in caught)


def test_dedupe_collision_post_ids() -> None:
    from app.core.jq_kb.chunkers.jq_strategy import chunk_jq_strategy_posts

    posts = [
        {**SAMPLE_POST, "post_id": 99, "title": "A", "source_file": "/a.txt"},
        {**SAMPLE_POST, "post_id": 99, "title": "B", "source_file": "/b.txt"},
    ]
    chunks = chunk_jq_strategy_posts(posts)
    post_ids = {c.post_id for c in chunks if c.layer.value == "summary"}
    assert len(post_ids) == 2


def test_chunk_with_set_key_params() -> None:
    code = (
        "def initialize(context):\n"
        "    g.symbols = {1, 2, 3}\n"
    )
    post = {**SAMPLE_POST, "code": code}
    chunks = chunk_jq_strategy_post(post)
    assert any(c.layer.value == "summary" for c in chunks)


def test_parse_strategy_txt_with_header(tmp_path: Path) -> None:
    content = (
        "# 克隆自聚宽文章：https://www.joinquant.com/post/99999\n"
        "# 标题：测试策略\n"
        "# 作者：作者A\n\n"
        "def initialize(context):\n    pass\n"
    )
    path = tmp_path / "sample.txt"
    path.write_text(content, encoding="utf-8")
    parsed = parse_strategy_txt(path)
    assert parsed["post_id"] == 99999
    assert parsed["title"] == "测试策略"
    assert "initialize" in parsed["code"]
