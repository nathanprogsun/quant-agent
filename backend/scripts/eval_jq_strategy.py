"""Retrieval eval for jq_strategy."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.jq_kb.llm import get_llm
from app.core.jq_kb.paths import EVAL_DATA_DIR, EVAL_REPORT_DIR
from app.core.jq_kb.retrievers import JqStrategyRetriever
from app.core.jq_kb.strategy_storage import JqStrategyStore
from app.settings import get_settings


def _load_questions(path: Path) -> list[dict]:
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def _recall_at_k(expected: int, hits: list, k: int) -> float:
    ids = [int(h.metadata.get("post_id", 0)) for h in hits[:k]]
    return 1.0 if expected in ids else 0.0


def _mrr(expected: int, hits: list) -> float:
    for i, h in enumerate(hits):
        if int(h.metadata.get("post_id", 0)) == expected:
            return 1.0 / (i + 1)
    return 0.0


def _build_eval_retriever() -> JqStrategyRetriever:
    return JqStrategyRetriever(JqStrategyStore(), llm=get_llm(temperature=0.0))


async def _run_eval(dataset: Path, *, k: int = 5) -> dict:
    settings = get_settings()
    retriever = _build_eval_retriever()
    questions = _load_questions(dataset)
    recalls: list[float] = []
    mrrs: list[float] = []
    failures: list[dict] = []

    for q in questions:
        hits = await retriever.retrieve(
            q["query"],
            year=int(q.get("year") or 0),
            strategy_type=q.get("strategy_type", ""),
            top_k=k,
        )
        expected = int(q.get("expected_post_id", 0))
        r = _recall_at_k(expected, hits, k)
        m = _mrr(expected, hits)
        recalls.append(r)
        mrrs.append(m)
        if r == 0:
            failures.append(
                {
                    "id": q["id"],
                    "query": q["query"],
                    "expected": expected,
                    "got": [h.metadata.get("post_id") for h in hits],
                    "titles": [h.metadata.get("title") for h in hits],
                }
            )

    return {
        "dataset": str(dataset),
        "llm_model": settings.model,
        "count": len(questions),
        f"recall@{k}": sum(recalls) / len(recalls) if recalls else 0.0,
        "mrr": sum(mrrs) / len(mrrs) if mrrs else 0.0,
        "failures": failures,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pilot", action="store_true")
    parser.add_argument("--k", type=int, default=5)
    args = parser.parse_args()

    dataset = EVAL_DATA_DIR / (
        "jq_strategy_eval_pilot.jsonl" if args.pilot else "jq_strategy_eval_full.jsonl"
    )
    if not dataset.is_file():
        raise FileNotFoundError(dataset)

    report = asyncio.run(_run_eval(dataset, k=args.k))
    EVAL_REPORT_DIR.mkdir(parents=True, exist_ok=True)
    out = EVAL_REPORT_DIR / f"retrieval_jq_strategy_{'pilot' if args.pilot else 'full'}.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps({k: report[k] for k in report if k != "failures"}, ensure_ascii=False, indent=2))
    if report["failures"]:
        print(f"Failures: {len(report['failures'])}")


if __name__ == "__main__":
    main()
