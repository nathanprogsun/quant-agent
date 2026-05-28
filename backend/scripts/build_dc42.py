"""DC42 knowledge base build pipeline.

Steps:
  01_ingest       → manifest.jsonl
  02_extract_code → staging/{id}.py
  03_llm_enrich   → L2 metadata
  04_llm_experience → L3 experience
  05_llm_relations → L4 relations
  06_parameter_stats → parameter_limits.json
  07_chunk_embed  → dc42.db + chroma_db/
  08_validate     → build_report.md
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def ingest(source_dir: Path, output_dir: Path) -> list[dict[str, Any]]:
    """01_ingest: Scan source directory, create manifest with file metadata."""
    manifest: list[dict[str, Any]] = []

    for year_dir in sorted(source_dir.iterdir()):
        if not year_dir.is_dir():
            continue
        year_match = re.search(r"(\d{4})", year_dir.name)
        year_bucket = year_match.group(1) if year_match else "unknown"

        for txt_file in sorted(year_dir.glob("*.txt")):
            content = txt_file.read_text(encoding="utf-8")
            file_hash = hashlib.sha256(content.encode()).hexdigest()[:16]
            entry = {
                "path": str(txt_file.relative_to(source_dir)),
                "hash": file_hash,
                "year_bucket": year_bucket,
                "strategy_name": txt_file.stem,
            }
            manifest.append(entry)

    manifest_path = output_dir / "manifest.jsonl"
    with open(manifest_path, "w", encoding="utf-8") as f:
        for entry in manifest:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    return manifest


def extract_code(
    manifest: list[dict[str, Any]],
    source_dir: Path,
    output_dir: Path,
) -> list[dict[str, Any]]:
    """02_extract_code: Extract Python code blocks from strategy files."""
    staging_dir = output_dir / "staging"
    staging_dir.mkdir(exist_ok=True)

    results: list[dict[str, Any]] = []
    code_pattern = re.compile(r"```python\s*\n(.*?)```", re.DOTALL)

    for entry in manifest:
        file_path = source_dir / entry["path"]
        content = file_path.read_text(encoding="utf-8")
        matches = code_pattern.findall(content)

        strategy_id = entry["hash"]
        if matches:
            code = matches[0].strip()
            code_path = staging_dir / f"{strategy_id}.py"
            code_path.write_text(code, encoding="utf-8")
            results.append({**entry, "code_status": "ok", "code": code, "code_path": str(code_path)})
        else:
            results.append({**entry, "code_status": "missing", "code": None, "code_path": None})

    return results


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Build DC42 knowledge base")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    manifest = ingest(source_dir=args.source, output_dir=args.output)
    results = extract_code(manifest=manifest, source_dir=args.source, output_dir=args.output)
    print(f"Ingested {len(manifest)} strategies, {sum(1 for r in results if r['code_status'] == 'ok')} with code")
