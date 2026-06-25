"""Import local strategy .txt files into jq_strategy raw JSON."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.jq_kb.parser.strategy_txt import load_all_strategies, parse_strategy_txt
from app.core.jq_kb.paths import JQ_STRATEGY_RAW_DIR

DEFAULT_DATA_DIR = Path(
    os.environ.get(
        "JQ_STRATEGY_DATA_DIR",
        "/Users/jung/Desktop/DC42-2022年度精选策略",
    )
)

PILOT_GLOBS = (
    "**/75.ETF轮动策略-入门2.0.txt",
    "**/66.ETF动量轮动MA乖离择时.txt",
    "**/76.ETF-控制回撤性能拉满（国债ETF增强).txt",
    "**/69.场内基金定投价值平均增强策略，年化30%+.txt",
    "**/10.龙头首阴战法改版二.txt",
    "**/26.近几年一直有效的股票BOLL择时策略.txt",
    "**/96.集合竞价量比策略V1.txt",
    "**/85.价值策略重开，再次向Jqz1226致敬.txt",
)


def _write_payload(path: Path, posts: list[dict], *, label: str) -> None:
    payload = {
        "version": f"{label}-{datetime.now(timezone.utc).date().isoformat()}",
        "source": str(DEFAULT_DATA_DIR),
        "count": len(posts),
        "posts": posts,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {path} ({len(posts)} posts)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Import jq_strategy txt to raw JSON")
    parser.add_argument("--pilot", action="store_true", help="Write pilot.json (8 ETF/strategy samples)")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    args = parser.parse_args()

    if not args.data_dir.is_dir():
        raise FileNotFoundError(f"JQ_STRATEGY_DATA_DIR not found: {args.data_dir}")

    if args.pilot:
        posts: list[dict] = []
        for pattern in PILOT_GLOBS:
            matches = sorted(args.data_dir.glob(pattern))
            if not matches:
                print(f"Warning: no match for {pattern}")
                continue
            posts.append(parse_strategy_txt(matches[0]))
        _write_payload(JQ_STRATEGY_RAW_DIR / "pilot.json", posts, label="pilot")
        return

    posts = load_all_strategies(args.data_dir)
    _write_payload(JQ_STRATEGY_RAW_DIR / "posts.json", posts, label="full")


if __name__ == "__main__":
    main()
