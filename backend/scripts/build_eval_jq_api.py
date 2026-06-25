"""Build jq_api eval datasets."""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.jq_kb.paths import EVAL_DATA_DIR

PILOT_SRC = EVAL_DATA_DIR / "jq_api_eval_pilot.jsonl"
FULL_SRC = EVAL_DATA_DIR / "jq_api_eval_full.jsonl"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["pilot", "full"], default="pilot")
    args = parser.parse_args()

    EVAL_DATA_DIR.mkdir(parents=True, exist_ok=True)
    if args.mode == "pilot":
        if not PILOT_SRC.is_file():
            raise FileNotFoundError(PILOT_SRC)
        with open(PILOT_SRC, encoding="utf-8") as f:
            n = sum(1 for _ in f)
        print(f"Pilot eval set ready: {PILOT_SRC} ({n} questions)")
        return

    if FULL_SRC.is_file():
        print(f"Full eval set ready: {FULL_SRC}")
        return
    shutil.copy(PILOT_SRC, FULL_SRC)
    print(f"Created full eval placeholder from pilot: {FULL_SRC}")


if __name__ == "__main__":
    main()
