"""DC42 build pipeline — ingest and extract steps."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.build_dc42 import (
    chunk_and_embed,
    compute_parameter_stats,
    extract_code,
    ingest,
    validate,
)


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


def test_compute_parameter_stats(tmp_path: Path) -> None:
    """06_parameter_stats should compute P10/P50/P90 for numeric parameters."""
    enriched = [
        {"hash": "a", "l2_parameters": {"stock_count": 5, "stop_loss": 0.1}},
        {"hash": "b", "l2_parameters": {"stock_count": 10, "stop_loss": 0.05}},
        {"hash": "c", "l2_parameters": {"stock_count": 20, "stop_loss": 0.15}},
        {"hash": "d", "l2_parameters": {"stock_count": 8, "stop_loss": 0.08}},
        {"hash": "e", "l2_parameters": {"stock_count": 15, "stop_loss": 0.12}},
    ]

    stats = compute_parameter_stats(enriched, output_dir=tmp_path)

    assert "stock_count" in stats
    assert "P10" in stats["stock_count"]
    assert "P50" in stats["stock_count"]
    assert "P90" in stats["stock_count"]
    assert stats["stock_count"]["P50"] == 10  # median of [5,8,10,15,20]


def test_chunk_and_embed_creates_db(tmp_path: Path) -> None:
    """07_chunk_embed should create SQLite and ChromaDB."""
    enriched = [
        {
            "hash": "abc123",
            "strategy_name": "test_strategy",
            "year_bucket": "2022",
            "l2_type": "small_cap",
            "l2_factors": ["market_cap"],
            "l2_parameters": {"n": 5},
            "l2_code_logic": "select smallest",
            "experience": "works in bull market",
            "failure_modes": ["liquidity risk"],
            "boundary_text": "stop loss 10%",
            "l4_similar": [],
            "l4_derived": [],
            "l4_complementary": [],
            "l4_substitute": [],
            "code": "def initialize(context): pass",
            "description": "test strategy",
            "code_status": "ok",
        },
    ]
    stats = {"n": {"P10": 3, "P50": 5, "P90": 20}}

    chunk_and_embed(enriched=enriched, stats=stats, output_dir=tmp_path)

    assert (tmp_path / "dc42.db").exists()


def test_validate_passes_when_outputs_exist(tmp_path: Path) -> None:
    """08_validate should pass when all outputs are present."""
    (tmp_path / "dc42.db").touch()
    (tmp_path / "chroma_db").mkdir()

    result = validate(output_dir=tmp_path)
    assert result is True


def test_validate_fails_when_output_missing(tmp_path: Path) -> None:
    """08_validate should fail when dc42.db is missing."""
    result = validate(output_dir=tmp_path)
    assert result is False
