"""DC42 knowledge retriever — vector search over ChromaDB."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from app.core.dc42.types import (
    Diagnosis,
    ParameterAnalysis,
    RetrievalResult,
    SimilarCase,
    StrategyChunk,
)


class DC42Retriever:
    """Retrieve DC42 strategy knowledge via vector search and metadata lookup."""

    def __init__(
        self,
        collection: Any,  # chromadb.Collection
        db_path: Path,
        parameter_stats: dict[str, dict[str, float]] | None = None,
    ) -> None:
        self._collection = collection
        self._db_path = db_path
        self._parameter_stats = parameter_stats or {}

    async def retrieve_by_intent(self, user_description: str) -> RetrievalResult:
        """Retrieve strategies matching user intent via vector search."""
        results = self._collection.query(
            query_texts=[user_description],
            n_results=5,
            where={"chunk_type": "intent"},
        )

        chunks = []
        strategy_names = []
        for i, doc in enumerate(results["documents"][0]):
            meta = results["metadatas"][0][i]
            chunk = StrategyChunk(
                chunk_id=results["ids"][0][i],
                strategy_id=meta.get("strategy_id", ""),
                chunk_type=meta.get("chunk_type", "intent"),
                content=doc,
                metadata=meta,
            )
            chunks.append(chunk)

        # Look up strategy names from DB
        if chunks:
            strategy_ids = list({c.strategy_id for c in chunks})
            with sqlite3.connect(str(self._db_path)) as conn:
                cursor = conn.cursor()
                placeholders = ",".join("?" * len(strategy_ids))
                cursor.execute(f"SELECT name FROM dc42_strategies WHERE id IN ({placeholders})", strategy_ids)
                strategy_names = [row[0] for row in cursor.fetchall()]

        summary = f"找到 {len(chunks)} 个相关 DC42 策略片段，涉及 {len(strategy_names)} 个策略"

        return RetrievalResult(
            chunks=chunks,
            strategy_names=strategy_names,
            summary=summary,
        )

    async def retrieve_by_parameters(self, params: dict[str, Any]) -> list[ParameterAnalysis]:
        """Check if user parameters are within DC42 validated ranges."""
        if not params:
            return [ParameterAnalysis(
                parameter="none", user_value=0, dc42_p10=0, dc42_p50=0, dc42_p90=0,
                in_range=True, recommendation="无参数需要检查",
            )]

        results: list[ParameterAnalysis] = []
        for key, value in params.items():
            if not isinstance(value, (int, float)):
                continue

            stats = self._parameter_stats.get(key, {})
            p10 = stats.get("P10", 0)
            p50 = stats.get("P50", 0)
            p90 = stats.get("P90", 0)

            in_range = p10 <= value <= p90 if p90 > 0 else True
            recommendation = (
                f"参数 {key}={value} 在 DC42 合理范围内 (P10={p10}, P90={p90})"
                if in_range
                else f"参数 {key}={value} 超出 DC42 经验范围 (P10={p10}, P90={p90})，建议调整"
            )

            results.append(ParameterAnalysis(
                parameter=key,
                user_value=float(value),
                dc42_p10=p10,
                dc42_p50=p50,
                dc42_p90=p90,
                in_range=in_range,
                recommendation=recommendation,
            ))

        return results if results else [ParameterAnalysis(
            parameter="none", user_value=0, dc42_p10=0, dc42_p50=0, dc42_p90=0,
            in_range=True, recommendation="无数值参数需要检查",
        )]

    async def retrieve_similar_strategy(self, code_or_description: str) -> SimilarCase:
        """Find the most similar DC42 strategy."""
        results = self._collection.query(
            query_texts=[code_or_description],
            n_results=1,
        )

        if not results["ids"][0]:
            return SimilarCase(
                strategy_id="", strategy_name="", similarity_score=0,
                summary="未找到相似策略", key_differences=[],
            )

        doc = results["documents"][0][0]
        meta = results["metadatas"][0][0]
        distance = results["distances"][0][0]
        similarity = max(0, 1 - distance)

        return SimilarCase(
            strategy_id=meta.get("strategy_id", ""),
            strategy_name=doc.split(":")[0] if ":" in doc else doc[:30],
            similarity_score=similarity,
            summary=doc[:200],
            key_differences=[],
        )

    async def retrieve_failure_pattern(self, error_type: str, metrics: dict[str, Any]) -> Diagnosis:
        """Diagnose backtest failure using DC42 experience patterns."""
        results = self._collection.query(
            query_texts=[error_type],
            n_results=3,
            where={"chunk_type": "experience"},
        )

        examples = [doc for doc in results["documents"][0]] if results["documents"][0] else []

        with sqlite3.connect(str(self._db_path)) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT failure_modes FROM dc42_strategies WHERE failure_modes != '[]' LIMIT 5")
            failure_modes = []
            for row in cursor.fetchall():
                try:
                    failure_modes.extend(json.loads(row[0]))
                except (json.JSONDecodeError, TypeError):
                    pass

        return Diagnosis(
            error_type=error_type,
            likely_causes=list(set(failure_modes))[:5] if failure_modes else ["未知原因"],
            dc42_examples=examples,
            fix_suggestions=[f"参考 DC42 经验: {ex[:100]}" for ex in examples[:2]],
        )
