"""Tests for jq_kb text length helpers."""

from __future__ import annotations

from app.core.jq_kb.chunkers.jq_strategy import chunk_jq_strategy_post
from app.core.jq_kb.utils import fit_text_for_embedding, split_text


def test_split_text_produces_multiple_parts() -> None:
    parts = split_text("a" * 7000, 3000)
    assert len(parts) == 3
    assert parts[0].endswith("...(截断)")
    assert parts[1].startswith("...(续)")


def test_fit_text_for_embedding_clamps() -> None:
    out = fit_text_for_embedding("x" * 100, max_chars=50)
    assert len(out) <= 50
    assert out.endswith("...(truncated for embedding)")


def test_long_function_splits_into_code_chunks() -> None:
    long_body = "    x = 1\n" * 2000
    post = {
        "post_id": 1,
        "year": 2024,
        "title": "长函数测试",
        "author": "test",
        "source_url": "https://example.com",
        "code": f"def initialize(context):\n{long_body}",
    }
    chunks = chunk_jq_strategy_post(post)
    code_chunks = [c for c in chunks if c.layer.value == "code"]
    assert len(code_chunks) >= 2
    assert all(len(c.contextual_content) <= 6000 for c in code_chunks)
