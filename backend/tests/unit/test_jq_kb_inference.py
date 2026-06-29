"""Unit tests for jq_kb embedding / rerank clients and postprocessor."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from llama_index.core.schema import NodeWithScore, TextNode

from app.core.jq_kb.embedding_client import embed_texts
from app.core.jq_kb.rerank_client import rerank_documents
from app.core.jq_kb.rerank_postprocessor import RerankPostprocessor


def test_embed_texts_parses_embedding_response() -> None:
    fake_response = type("R", (), {
        "status_code": 200,
        "raise_for_status": lambda self: None,
        "json": lambda self: {
            "data": [
                {"index": 1, "embedding": [0.2, 0.3]},
                {"index": 0, "embedding": [0.1, 0.1]},
            ]
        },
    })()
    with patch("app.core.jq_kb.embedding_client.get_http_client") as client:
        client.return_value.post.return_value = fake_response
        with patch("app.core.jq_kb.embedding_client._embedding_settings", return_value=("k", "https://x", "m")):
            vectors = embed_texts(["a", "b"])
    assert vectors == [[0.1, 0.1], [0.2, 0.3]]


def test_rerank_documents_returns_results() -> None:
    fake_response = type("R", (), {"raise_for_status": lambda self: None, "json": lambda self: {
        "results": [{"index": 0, "relevance_score": 0.9}]
    }})()
    with patch("app.core.jq_kb.rerank_client.get_http_client") as client:
        client.return_value.post.return_value = fake_response
        with patch("app.core.jq_kb.rerank_client._rerank_settings", return_value=("k", "https://x/rerank", "m")):
            results = rerank_documents(query="q", documents=["a"], top_n=1)
    assert results[0]["index"] == 0


def test_rerank_postprocessor_reorders_nodes() -> None:
    nodes = [
        NodeWithScore(node=TextNode(text="low"), score=0.1),
        NodeWithScore(node=TextNode(text="high"), score=0.2),
    ]
    reranker = RerankPostprocessor(top_n=1)
    with patch(
        "app.core.jq_kb.rerank_postprocessor.rerank_documents",
        return_value=[{"index": 1, "relevance_score": 0.95}],
    ):
        out = reranker.postprocess_nodes(nodes, query_str="q")
    assert len(out) == 1
    assert out[0].node.get_content() == "high"
    assert out[0].score == pytest.approx(0.95)
