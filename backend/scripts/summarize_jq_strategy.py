"""LLM 8-dim summaries for jq_strategy (resumable via summaries.jsonl)."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from langchain_core.messages import HumanMessage, SystemMessage

from app.core.jq_kb.ast_parser import extract_entities
from app.core.jq_kb.llm import get_llm
from app.core.jq_kb.paths import JQ_STRATEGY_RAW_DIR, JQ_STRATEGY_SUMMARIES_PATH
from app.core.jq_kb.schemas import StrategySummary

SUMMARY_SYSTEM = """你是量化策略分析专家。根据聚宽策略源码生成结构化摘要。
只输出 JSON，字段: strategy_type, one_line, factors, key_params, code_dependencies,
risk_handling, backtest_claimed, applicable_market, failure_modes。"""


def _load_posts(*, pilot: bool) -> list[dict]:
    path = JQ_STRATEGY_RAW_DIR / ("pilot.json" if pilot else "posts.json")
    if not path.is_file():
        path = JQ_STRATEGY_RAW_DIR / "pilot.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("posts", [])


def _load_existing() -> dict[int, dict]:
    if not JQ_STRATEGY_SUMMARIES_PATH.is_file():
        return {}
    out: dict[int, dict] = {}
    for line in JQ_STRATEGY_SUMMARIES_PATH.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            out[int(row["post_id"])] = row
    return out


async def _summarize_one(post: dict) -> StrategySummary:
    entities = extract_entities(post.get("code") or "")
    llm = get_llm(temperature=0.0).with_structured_output(StrategySummary)
    prompt = (
        f"post_id={post['post_id']}\n"
        f"标题: {post.get('title')}\n"
        f"年份: {post.get('year')}\n"
        f"函数: {', '.join(entities.get('functions', [])[:20])}\n"
        f"API: {', '.join(entities.get('factors_called', [])[:30])}\n"
        f"关键参数: {json.dumps(entities.get('key_params', {}), ensure_ascii=False)}\n\n"
        f"源码(截断):\n{(post.get('code') or '')[:6000]}"
    )
    result = await llm.ainvoke(
        [SystemMessage(content=SUMMARY_SYSTEM), HumanMessage(content=prompt)]
    )
    if isinstance(result, StrategySummary):
        result.post_id = int(post["post_id"])
        return result
    parsed = StrategySummary.model_validate({**result, "post_id": int(post["post_id"])})
    return parsed


async def run(*, pilot: bool, limit: int, force: bool) -> None:
    posts = _load_posts(pilot=pilot)
    existing = _load_existing() if not force else {}
    JQ_STRATEGY_SUMMARIES_PATH.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if JQ_STRATEGY_SUMMARIES_PATH.is_file() and not force else "w"
    processed = 0
    with open(JQ_STRATEGY_SUMMARIES_PATH, mode, encoding="utf-8") as fh:
        for post in posts:
            pid = int(post["post_id"])
            if pid in existing and not force:
                continue
            if limit and processed >= limit:
                break
            summary = await _summarize_one(post)
            fh.write(summary.model_dump_json(ensure_ascii=False) + "\n")
            fh.flush()
            processed += 1
            print(f"Summarized post_id={pid} ({summary.strategy_type})")
    print(f"Done. wrote {processed} summaries -> {JQ_STRATEGY_SUMMARIES_PATH}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pilot", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    asyncio.run(run(pilot=args.pilot, limit=args.limit, force=args.force))


if __name__ == "__main__":
    main()
