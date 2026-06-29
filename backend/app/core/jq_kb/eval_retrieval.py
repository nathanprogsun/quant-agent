"""Retrieval evaluation for jq_kb libraries."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Literal

from app.core.jq_kb.dict_storage import JqDictStore
from app.core.jq_kb.eval_datasets import JQ_API_EVAL, JQ_DICT_EVAL, JQ_STRATEGY_EVAL
from app.core.jq_kb.llm import get_llm
from app.core.jq_kb.paths import EVAL_REPORT_DIR
from app.core.jq_kb.retrievers import JqApiRetriever, JqDictRetriever, JqStrategyRetriever
from app.core.jq_kb.storage import JqApiStore
from app.core.jq_kb.strategy_storage import JqStrategyStore
from app.settings import get_settings

logger = logging.getLogger(__name__)

Library = Literal["jq_api", "jq_dict", "jq_strategy"]


def _load_questions(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _recall_at_k(expected: str, hits: list[Any], k: int, *, field: str) -> float:
    values = [str(h.metadata.get(field, "")) for h in hits[:k]]
    return 1.0 if expected in values else 0.0


def _mrr(expected: str, hits: list[Any], *, field: str) -> float:
    for i, h in enumerate(hits):
        if str(h.metadata.get(field, "")) == expected:
            return 1.0 / (i + 1)
    return 0.0


async def eval_jq_api(*, k: int = 5, dataset: Path = JQ_API_EVAL) -> dict[str, Any]:
    retriever = JqApiRetriever(JqApiStore(), llm=get_llm(temperature=0.0))
    return await _run_eval(
        retriever,
        dataset,
        k=k,
        expected_field="function_name",
        query_key="query",
        expected_key="expected_function",
    )


async def eval_jq_dict(*, k: int = 5, dataset: Path = JQ_DICT_EVAL) -> dict[str, Any]:
    retriever = JqDictRetriever(JqDictStore(), llm=get_llm(temperature=0.0))
    return await _run_eval(
        retriever,
        dataset,
        k=k,
        expected_field="code",
        query_key="query",
        expected_key="expected_code",
    )


async def eval_jq_strategy(*, k: int = 5, dataset: Path = JQ_STRATEGY_EVAL) -> dict[str, Any]:
    retriever = JqStrategyRetriever(JqStrategyStore(), llm=get_llm(temperature=0.0))
    questions = _load_questions(dataset)
    recalls: list[float] = []
    mrrs: list[float] = []
    failures: list[dict[str, Any]] = []

    for q in questions:
        hits = await retriever.retrieve(q["query"], top_k=k)
        expected = str(q.get("expected_post_id", ""))
        got = [str(h.metadata.get("post_id", "")) for h in hits[:k]]
        r = 1.0 if expected in got else 0.0
        m = 0.0
        for i, h in enumerate(hits):
            if str(h.metadata.get("post_id", "")) == expected:
                m = 1.0 / (i + 1)
                break
        recalls.append(r)
        mrrs.append(m)
        if r == 0:
            failures.append({"id": q["id"], "query": q["query"], "expected": expected, "got": got})

    settings = get_settings()
    return {
        "library": "jq_strategy",
        "dataset": str(dataset),
        "llm_model": settings.model,
        "count": len(questions),
        f"recall@{k}": sum(recalls) / len(recalls) if recalls else 0.0,
        "mrr": sum(mrrs) / len(mrrs) if mrrs else 0.0,
        "failures": failures,
    }


async def _run_eval(
    retriever: Any,
    dataset: Path,
    *,
    k: int,
    expected_field: str,
    query_key: str,
    expected_key: str,
) -> dict[str, Any]:
    settings = get_settings()
    questions = _load_questions(dataset)
    recalls: list[float] = []
    mrrs: list[float] = []
    failures: list[dict[str, Any]] = []

    for q in questions:
        hits = await retriever.retrieve(q[query_key], top_k=k)
        expected = str(q.get(expected_key, ""))
        r = _recall_at_k(expected, hits, k, field=expected_field)
        m = _mrr(expected, hits, field=expected_field)
        recalls.append(r)
        mrrs.append(m)
        if r == 0:
            failures.append(
                {
                    "id": q.get("id"),
                    "query": q[query_key],
                    "expected": expected,
                    "got": [h.metadata.get(expected_field) for h in hits],
                }
            )

    library = dataset.stem.replace("_eval", "")
    return {
        "library": library,
        "dataset": str(dataset),
        "llm_model": settings.model,
        "count": len(questions),
        f"recall@{k}": sum(recalls) / len(recalls) if recalls else 0.0,
        "mrr": sum(mrrs) / len(mrrs) if mrrs else 0.0,
        "failures": failures,
    }


async def eval_all(*, k: int = 5) -> dict[str, dict[str, Any]]:
    logger.info("eval jq_api (%d questions)", len(_load_questions(JQ_API_EVAL)))
    logger.info("eval jq_dict (%d questions)", len(_load_questions(JQ_DICT_EVAL)))
    logger.info("eval jq_strategy (%d questions)", len(_load_questions(JQ_STRATEGY_EVAL)))
    results = {
        "jq_api": await eval_jq_api(k=k),
        "jq_dict": await eval_jq_dict(k=k),
        "jq_strategy": await eval_jq_strategy(k=k),
    }
    EVAL_REPORT_DIR.mkdir(parents=True, exist_ok=True)
    for name, report in results.items():
        out = EVAL_REPORT_DIR / f"retrieval_{name}.json"
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info(
            "%s recall@%d=%.3f mrr=%.3f failures=%d",
            name,
            k,
            report[f"recall@{k}"],
            report["mrr"],
            len(report.get("failures", [])),
        )
    return results


def run_eval_all(*, k: int = 5) -> dict[str, dict[str, Any]]:
    return asyncio.run(eval_all(k=k))
