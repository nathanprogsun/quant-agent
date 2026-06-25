"""Tests for jq_dict eval dataset builder."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from scripts.build_eval_jq_dict import (
    FULL_EXTRA_QUESTIONS,
    FULL_OUT,
    FULL_JSON,
    PILOT_OUT,
    PILOT_QUESTIONS,
    build_full,
    build_pilot,
    load_corpus_codes,
)


@pytest.fixture
def corpus() -> set[str]:
    if not FULL_JSON.is_file():
        pytest.skip("full.json not present")
    return load_corpus_codes()


def test_all_curated_codes_exist_in_corpus(corpus: set[str]) -> None:
    build_pilot(corpus)
    build_full(corpus)


def test_pilot_and_full_jsonl_match_builder(corpus: set[str]) -> None:
    if not PILOT_OUT.is_file() or not FULL_OUT.is_file():
        pytest.skip("eval jsonl not generated yet")

    pilot_rows = [json.loads(line) for line in PILOT_OUT.read_text().splitlines() if line.strip()]
    full_rows = [json.loads(line) for line in FULL_OUT.read_text().splitlines() if line.strip()]

    assert len(pilot_rows) == len(PILOT_QUESTIONS)
    assert len(full_rows) == len(PILOT_QUESTIONS) + len(FULL_EXTRA_QUESTIONS)
    assert {r["expected_code"] for r in pilot_rows}.issubset(corpus)
