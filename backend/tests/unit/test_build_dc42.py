"""DC42 build pipeline — ingest and extract steps."""

from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path

import pytest

from scripts.build_dc42 import ingest, extract_code


@pytest.fixture
def sample_strategy_dir(tmp_path: Path) -> Path:
    """Create a sample strategy directory with .txt files."""
    year_dir = tmp_path / "2022年度精选策略"
    year_dir.mkdir()

    # Strategy with code block
    (year_dir / "1.小市值策略.txt").write_text(
        "# 小市值策略\n\n```python\nimport jqdatastd as jq\n\ndef initialize(context):\n    context.stock_count = 5\n\ndef handle_data(context, data):\n    pass\n```\n\n策略描述：选取市值最小的股票。"
    )

    # Strategy without code block
    (year_dir / "2.纯文本策略.txt").write_text(
        "# 轮动策略\n\n这是一个轮动策略的描述，没有代码。"
    )

    return tmp_path


def test_ingest_creates_manifest(sample_strategy_dir: Path, tmp_path: Path) -> None:
    """01_ingest should create manifest.jsonl with file metadata."""
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    manifest = ingest(source_dir=sample_strategy_dir, output_dir=output_dir)

    assert len(manifest) == 2
    assert manifest[0]["year_bucket"] == "2022"
    assert "path" in manifest[0]
    assert "hash" in manifest[0]


def test_ingest_hash_is_stable(sample_strategy_dir: Path, tmp_path: Path) -> None:
    """Running ingest twice should produce the same hashes."""
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    manifest1 = ingest(source_dir=sample_strategy_dir, output_dir=output_dir)
    manifest2 = ingest(source_dir=sample_strategy_dir, output_dir=output_dir)

    assert manifest1[0]["hash"] == manifest2[0]["hash"]


def test_extract_code_finds_python_block(sample_strategy_dir: Path, tmp_path: Path) -> None:
    """02_extract_code should extract Python code blocks."""
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    manifest = ingest(source_dir=sample_strategy_dir, output_dir=output_dir)
    results = extract_code(manifest=manifest, source_dir=sample_strategy_dir, output_dir=output_dir)

    code_results = [r for r in results if r["code_status"] == "ok"]
    assert len(code_results) == 1
    assert "import" in code_results[0]["code"]


def test_extract_code_marks_missing(sample_strategy_dir: Path, tmp_path: Path) -> None:
    """02_extract_code should mark strategies without code as 'missing'."""
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    manifest = ingest(source_dir=sample_strategy_dir, output_dir=output_dir)
    results = extract_code(manifest=manifest, source_dir=sample_strategy_dir, output_dir=output_dir)

    missing = [r for r in results if r["code_status"] == "missing"]
    assert len(missing) == 1
