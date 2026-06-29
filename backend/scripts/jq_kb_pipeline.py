"""Full jq_kb pipeline: ingest (all libraries) → eval."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.jq_kb.cli_logging import configure_cli_logging, flush_inference_progress
from app.core.jq_kb.eval_datasets import ensure_eval_datasets
from app.core.jq_kb.eval_retrieval import run_eval_all
from app.core.jq_kb.ingest import run_ingest_all

configure_cli_logging()
logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="jq_kb full ingest → eval pipeline")
    parser.add_argument("--reset", action="store_true", help="Wipe chroma/bm25 before ingest")
    parser.add_argument("--skip-ingest", action="store_true")
    parser.add_argument("--skip-eval", action="store_true")
    parser.add_argument("--only", choices=["jq_api", "jq_dict", "jq_strategy"], help="Ingest a single library")
    parser.add_argument("--k", type=int, default=5, help="Recall@K for retrieval eval")
    args = parser.parse_args()

    if not args.skip_ingest:
        logger.info("=== jq_kb ingest (full corpus) ===")
        counts = run_ingest_all(reset=args.reset, only=args.only)
        flush_inference_progress()
        print(json.dumps({"ingest": counts}, ensure_ascii=False, indent=2))

    ensure_eval_datasets()

    if not args.skip_eval:
        logger.info("=== jq_kb retrieval eval ===")
        reports = run_eval_all(k=args.k)
        summary = {
            lib: {k: v for k, v in rep.items() if k != "failures"}
            for lib, rep in reports.items()
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
