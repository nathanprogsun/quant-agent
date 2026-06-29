"""Verify jq_kb committed artifacts and eval datasets exist."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.core.jq_kb.paths import (
    EVAL_DATA_DIR,
    JQ_API_MANIFEST_PATH,
    JQ_DICT_MANIFEST_PATH,
    JQ_STRATEGY_MANIFEST_PATH,
)


@pytest.mark.parametrize(
    ("manifest_path", "library"),
    [
        (JQ_API_MANIFEST_PATH, "jq_api"),
        (JQ_DICT_MANIFEST_PATH, "jq_dict"),
        (JQ_STRATEGY_MANIFEST_PATH, "jq_strategy"),
    ],
)
def test_jq_kb_manifest_present(manifest_path: Path, library: str) -> None:
    assert manifest_path.is_file(), f"missing manifest for {library}"
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert data["library"] == library
    assert data.get("chunks_count", 0) > 0


@pytest.mark.parametrize(
    "dataset_name",
    [
        "jq_api_eval.jsonl",
        "jq_dict_eval.jsonl",
        "jq_strategy_eval.jsonl",
    ],
)
def test_jq_kb_eval_datasets_present(dataset_name: str) -> None:
    path = EVAL_DATA_DIR / dataset_name
    assert path.is_file()
    lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) >= 5
