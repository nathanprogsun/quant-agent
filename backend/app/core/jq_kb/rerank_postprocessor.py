"""LlamaIndex rerank postprocessor for jq_kb retrieval."""

from __future__ import annotations

from typing import Any

from llama_index.core.bridge.pydantic import Field
from llama_index.core.postprocessor.types import BaseNodePostprocessor
from llama_index.core.schema import NodeWithScore, QueryBundle

from app.core.jq_kb.rerank_client import rerank_documents


class RerankPostprocessor(BaseNodePostprocessor):  # type: ignore[misc]  # BaseNodePostprocessor typed as Any (stub missing)
    """Cross-encoder rerank step in jq_kb hybrid retrieval."""

    top_n: int = Field(default=5, ge=1)

    def __init__(self, top_n: int = 5, **kwargs: Any) -> None:
        super().__init__(top_n=top_n, **kwargs)

    @classmethod
    def class_name(cls) -> str:
        return "JqKbRerankPostprocessor"

    def _postprocess_nodes(
        self,
        nodes: list[NodeWithScore],
        query_bundle: QueryBundle | None = None,
    ) -> list[NodeWithScore]:
        if not nodes or query_bundle is None:
            return nodes

        documents = [node.node.get_content(metadata_mode="none") for node in nodes]
        results = rerank_documents(
            query=query_bundle.query_str,
            documents=documents,
            top_n=self.top_n,
        )

        reranked: list[NodeWithScore] = []
        for item in results:
            idx = int(item["index"])
            if idx < 0 or idx >= len(nodes):
                continue
            node = nodes[idx]
            score = float(item.get("relevance_score", node.score or 0.0))
            reranked.append(NodeWithScore(node=node.node, score=score))
        return reranked or nodes[: self.top_n]
