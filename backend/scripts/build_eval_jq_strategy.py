"""Build jq_strategy eval datasets from pilot.json post_ids."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.jq_kb.paths import EVAL_DATA_DIR, JQ_STRATEGY_RAW_DIR

PILOT_QUESTIONS: list[dict[str, Any]] = [
    {"id": "s001", "query": "ETF轮动策略入门", "expected_post_id": 0, "category": "etf", "difficulty": "easy"},
    {"id": "s002", "query": "ETF动量轮动 MA乖离择时", "expected_post_id": 0, "category": "etf", "difficulty": "medium"},
    {"id": "s003", "query": "国债ETF增强控制回撤", "expected_post_id": 0, "category": "etf", "difficulty": "medium"},
    {"id": "s004", "query": "场内基金定投价值平均", "expected_post_id": 0, "category": "etf", "difficulty": "medium"},
    {"id": "s005", "query": "龙头首阴战法", "expected_post_id": 0, "category": "stock", "difficulty": "easy"},
    {"id": "s006", "query": "BOLL择时策略", "expected_post_id": 0, "category": "timing", "difficulty": "easy"},
    {"id": "s007", "query": "集合竞价量比策略", "expected_post_id": 0, "category": "auction", "difficulty": "medium"},
    {"id": "s008", "query": "initialize 函数 set_benchmark 沪深300", "expected_post_id": 0, "category": "code", "difficulty": "hard"},
]

# Map stable titles -> question indices (filled from pilot.json at build time)
TITLE_TO_QID: dict[str, str] = {
    "ETF轮动策略-入门2.0": "s001",
    "ETF动量轮动MA乖离择时": "s002",
    "ETF-控制回撤性能拉满（国债ETF增强）": "s003",
    "场内基金定投价值平均增强策略，年化30%+": "s004",
    "龙头首阴战法改版二": "s005",
    "近几年一直有效的股票BOLL择时策略": "s006",
    "集合竞价量比策略V1": "s007",
    "价值策略重开，再次向Jqz1226致敬": "s008",
}


def _resolve_post_ids() -> dict[str, int]:
    pilot_path = JQ_STRATEGY_RAW_DIR / "pilot.json"
    if not pilot_path.is_file():
        raise FileNotFoundError(pilot_path)
    posts = json.loads(pilot_path.read_text())["posts"]
    return {p["title"]: int(p["post_id"]) for p in posts}


def build_questions() -> list[dict[str, Any]]:
    title_to_pid = _resolve_post_ids()
    out: list[dict[str, Any]] = []
    for q in PILOT_QUESTIONS:
        row = dict(q)
        for title, qid in TITLE_TO_QID.items():
            if row["id"] == qid and title in title_to_pid:
                row["expected_post_id"] = title_to_pid[title]
                break
        if not row["expected_post_id"]:
            raise ValueError(f"Could not resolve post_id for {row['id']}")
        out.append(row)
    return out


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["pilot", "full"], default="pilot")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    questions = build_questions()
    pilot_out = EVAL_DATA_DIR / "jq_strategy_eval_pilot.jsonl"
    full_out = EVAL_DATA_DIR / "jq_strategy_eval_full.jsonl"

    if args.mode in ("pilot", "full"):
        _write_jsonl(pilot_out, questions)
        print(f"Wrote {pilot_out} ({len(questions)} questions)")

    if args.mode == "full":
        if full_out.is_file() and not args.force:
            print(f"Full exists: {full_out}")
        else:
            _write_jsonl(full_out, questions)
            print(f"Wrote {full_out} (pilot placeholder)")


if __name__ == "__main__":
    main()
