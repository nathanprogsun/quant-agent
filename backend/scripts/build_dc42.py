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

import asyncio
import hashlib
import json
import re
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

LLMCall = Callable[[str], Awaitable[Any]]


def _read_text(path: Path) -> str:
    """Read strategy text with common Chinese encodings."""
    for encoding in ("utf-8", "gb18030", "gbk"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return path.read_text(encoding="utf-8", errors="replace")


def ingest(source_dir: Path, output_dir: Path) -> list[dict[str, Any]]:
    """01_ingest: Scan source directory, create manifest with file metadata."""
    manifest: list[dict[str, Any]] = []

    for year_dir in sorted(source_dir.iterdir()):
        if not year_dir.is_dir():
            continue
        year_match = re.search(r"(\d{4})", year_dir.name)
        year_bucket = year_match.group(1) if year_match else "unknown"

        for txt_file in sorted(year_dir.glob("*.txt")):
            content = _read_text(txt_file)
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
        content = _read_text(file_path)
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


async def llm_enrich(
    extracted: list[dict[str, Any]],
    llm_call: LLMCall,
    output_dir: Path,
    concurrency: int = 5,
) -> list[dict[str, Any]]:
    """03_llm_enrich: L2 pattern layer — type, factors, parameters, code_logic."""
    semaphore = asyncio.Semaphore(concurrency)

    async def process_one(item: dict[str, Any]) -> dict[str, Any]:
        async with semaphore:
            prompt = f"""分析以下量化策略，返回JSON:
策略名: {item['strategy_name']}
描述: {item.get('description', '')}
代码: {item.get('code', '无')[:2000]}

返回格式:
{{"type": "策略类型", "factors": ["因子列表"], "parameters": {{"参数名": 默认值}}, "code_logic": "核心逻辑"}}"""

            response = await llm_call(prompt)
            text = response.content if hasattr(response, "content") else str(response)
            try:
                data = json.loads(text)
            except (json.JSONDecodeError, TypeError):
                data = {"type": "unknown", "factors": [], "parameters": {}, "code_logic": ""}

            return {
                **item,
                "l2_type": data.get("type", "unknown"),
                "l2_factors": data.get("factors", []),
                "l2_parameters": data.get("parameters", {}),
                "l2_code_logic": data.get("code_logic", ""),
            }

    tasks = [process_one(item) for item in extracted]
    enriched = await asyncio.gather(*tasks)

    output_path = output_dir / "enriched_l2.jsonl"
    with open(output_path, "w", encoding="utf-8") as f:
        for entry in enriched:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    return list(enriched)


async def llm_experience(
    enriched: list[dict[str, Any]],
    llm_call: LLMCall,
    output_dir: Path,
    concurrency: int = 5,
) -> list[dict[str, Any]]:
    """04_llm_experience: L3 experience layer + L5 boundary text."""
    semaphore = asyncio.Semaphore(concurrency)

    async def process_one(item: dict[str, Any]) -> dict[str, Any]:
        async with semaphore:
            prompt = f"""基于以下策略信息，分析实战经验:
策略名: {item['strategy_name']}
类型: {item.get('l2_type', 'unknown')}
因子: {item.get('l2_factors', [])}

返回JSON:
{{"experience": "实战经验总结", "failure_modes": ["失效模式1", "失效模式2"], "boundary_text": "边界条件"}}"""

            response = await llm_call(prompt)
            text = response.content if hasattr(response, "content") else str(response)
            try:
                data = json.loads(text)
            except (json.JSONDecodeError, TypeError):
                data = {"experience": "", "failure_modes": [], "boundary_text": ""}

            return {
                **item,
                "experience": data.get("experience", ""),
                "failure_modes": data.get("failure_modes", []),
                "boundary_text": data.get("boundary_text", ""),
            }

    tasks = [process_one(item) for item in enriched]
    results = await asyncio.gather(*tasks)

    output_path = output_dir / "enriched_l3.jsonl"
    with open(output_path, "w", encoding="utf-8") as f:
        for entry in results:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    return list(results)


async def llm_relations(
    enriched: list[dict[str, Any]],
    llm_call: LLMCall,
    output_dir: Path,
    concurrency: int = 5,
) -> list[dict[str, Any]]:
    """05_llm_relations: L4 relation layer."""
    semaphore = asyncio.Semaphore(concurrency)
    all_names = [item["strategy_name"] for item in enriched]

    async def process_one(item: dict[str, Any]) -> dict[str, Any]:
        async with semaphore:
            prompt = f"""分析策略关系:
策略名: {item['strategy_name']}
类型: {item.get('l2_type', 'unknown')}
所有策略: {all_names[:50]}

返回JSON:
{{"similar": ["相似策略名"], "derived": ["衍生策略名"], "complementary": ["互补策略名"], "substitute": ["替代策略名"]}}"""

            response = await llm_call(prompt)
            text = response.content if hasattr(response, "content") else str(response)
            try:
                data = json.loads(text)
            except (json.JSONDecodeError, TypeError):
                data = {"similar": [], "derived": [], "complementary": [], "substitute": []}

            return {
                **item,
                "l4_similar": data.get("similar", []),
                "l4_derived": data.get("derived", []),
                "l4_complementary": data.get("complementary", []),
                "l4_substitute": data.get("substitute", []),
            }

    tasks = [process_one(item) for item in enriched]
    results = await asyncio.gather(*tasks)

    output_path = output_dir / "enriched_l4.jsonl"
    with open(output_path, "w", encoding="utf-8") as f:
        for entry in results:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    return list(results)


def compute_parameter_stats(
    enriched: list[dict[str, Any]],
    output_dir: Path,
) -> dict[str, dict[str, float]]:
    """06_parameter_stats: Compute P10/P50/P90 for numeric parameters."""
    param_values: dict[str, list[float]] = {}

    for item in enriched:
        for key, value in item.get("l2_parameters", {}).items():
            if isinstance(value, (int, float)):
                param_values.setdefault(key, []).append(float(value))

    import statistics

    stats: dict[str, dict[str, float]] = {}
    for param, values in param_values.items():
        sorted_vals = sorted(values)
        n = len(sorted_vals)
        stats[param] = {
            "P10": sorted_vals[max(0, int(n * 0.1))],
            "P50": statistics.median(sorted_vals),
            "P90": sorted_vals[min(n - 1, int(n * 0.9))],
            "min": min(sorted_vals),
            "max": max(sorted_vals),
        }

    output_path = output_dir / "parameter_limits.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)

    return stats


def chunk_and_embed(
    enriched: list[dict[str, Any]],
    stats: dict[str, dict[str, float]],
    output_dir: Path,
) -> None:
    """07_chunk_embed: Create SQLite metadata DB and ChromaDB vectors."""
    import sqlite3

    import chromadb

    db_path = output_dir / "dc42.db"
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS dc42_strategies (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            year_bucket TEXT,
            type TEXT,
            factors TEXT,
            parameters TEXT,
            code_logic TEXT,
            experience TEXT,
            failure_modes TEXT,
            boundary_text TEXT,
            code TEXT,
            description TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS dc42_chunks (
            id TEXT PRIMARY KEY,
            strategy_id TEXT NOT NULL,
            chunk_type TEXT NOT NULL,
            content TEXT NOT NULL,
            metadata TEXT,
            FOREIGN KEY (strategy_id) REFERENCES dc42_strategies(id)
        )
    """)

    # ChromaDB setup
    chroma_path = str(output_dir / "chroma_db")
    chroma_client = chromadb.PersistentClient(path=chroma_path)
    collection = chroma_client.get_or_create_collection(
        name="dc42_chunks",
        metadata={"hnsw:space": "cosine"},
    )

    chunk_ids: list[str] = []
    chunk_docs: list[str] = []
    chunk_metas: list[dict[str, str]] = []

    for item in enriched:
        sid = item["hash"]
        cursor.execute(
            "INSERT OR REPLACE INTO dc42_strategies VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                sid,
                item["strategy_name"],
                item.get("year_bucket", ""),
                item.get("l2_type", ""),
                json.dumps(item.get("l2_factors", []), ensure_ascii=False),
                json.dumps(item.get("l2_parameters", {}), ensure_ascii=False),
                item.get("l2_code_logic", ""),
                item.get("experience", ""),
                json.dumps(item.get("failure_modes", []), ensure_ascii=False),
                item.get("boundary_text", ""),
                item.get("code", ""),
                item.get("description", ""),
            ),
        )

        # Create chunks for different retrieval strategies
        chunk_types = [
            ("intent", f"{item['strategy_name']}: {item.get('description', '')}"),
            ("factor", f"Factors: {', '.join(item.get('l2_factors', []))}"),
            ("experience", f"Experience: {item.get('experience', '')}"),
        ]
        for chunk_type, content in chunk_types:
            if content and len(content) > 10:
                chunk_id = f"{sid}_{chunk_type}"
                cursor.execute(
                    "INSERT OR REPLACE INTO dc42_chunks VALUES (?, ?, ?, ?, ?)",
                    (chunk_id, sid, chunk_type, content, "{}"),
                )
                chunk_ids.append(chunk_id)
                chunk_docs.append(content)
                chunk_metas.append({
                    "strategy_id": sid,
                    "strategy_name": item["strategy_name"],
                    "chunk_type": chunk_type,
                    "year_bucket": item.get("year_bucket", ""),
                })

    conn.commit()
    conn.close()

    # Batch insert into ChromaDB (max batch size 5461 for default settings)
    batch_size = 5000
    for i in range(0, len(chunk_ids), batch_size):
        collection.add(
            ids=chunk_ids[i : i + batch_size],
            documents=chunk_docs[i : i + batch_size],
            metadatas=chunk_metas[i : i + batch_size],  # type: ignore[arg-type]
        )

    print(f"ChromaDB: {collection.count()} chunks embedded in {chroma_path}")


def build_without_llm(extracted: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build minimal enriched records without LLM (code-only metadata)."""
    enriched: list[dict[str, Any]] = []
    for item in extracted:
        if item.get("code_status") != "ok":
            continue
        enriched.append(
            {
                **item,
                "description": item["strategy_name"],
                "l2_type": "unknown",
                "l2_factors": [],
                "l2_parameters": {},
                "l2_code_logic": "",
                "experience": "",
                "failure_modes": [],
                "boundary_text": "",
            }
        )
    return enriched


def load_staging_extracts(staging_dir: Path) -> list[dict[str, Any]]:
    """Load pre-extracted strategy code from an existing staging directory."""
    manifest_path = staging_dir / "manifest.jsonl"
    if not manifest_path.is_file():
        msg = f"missing manifest: {manifest_path}"
        raise FileNotFoundError(msg)

    enriched: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for line in manifest_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        entry = json.loads(line)
        if entry.get("code_status") != "ok":
            continue

        strategy_id = entry["id"]
        if strategy_id in seen_ids:
            continue
        seen_ids.add(strategy_id)
        code_path = staging_dir / f"{strategy_id}.py"
        if not code_path.is_file():
            continue

        code = _read_text(code_path)
        item: dict[str, Any] = {
            "hash": strategy_id,
            "strategy_name": entry.get("title", strategy_id),
            "year_bucket": entry.get("year_bucket", ""),
            "description": entry.get("title", ""),
            "code": code,
            "code_status": "ok",
            "l2_type": "unknown",
            "l2_factors": [],
            "l2_parameters": {},
            "l2_code_logic": "",
            "experience": "",
            "failure_modes": [],
            "boundary_text": "",
        }

        meta_path = staging_dir / f"{strategy_id}.meta.json"
        if meta_path.is_file():
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            llm = meta.get("llm_extraction", {})
            item["l2_type"] = llm.get("type", "unknown")
            factors = llm.get("factors", [])
            item["l2_factors"] = [
                factor["name"] if isinstance(factor, dict) else str(factor) for factor in factors
            ]
            item["l2_parameters"] = llm.get("parameters", {})
            item["l2_code_logic"] = llm.get("code_logic", "")

        enriched.append(item)

    return enriched


def validate(output_dir: Path) -> bool:
    """08_validate: Check that all required outputs exist."""
    required = ["dc42.db", "chroma_db"]
    for name in required:
        path = output_dir / name
        if not path.exists():
            print(f"FAIL: missing {name}")
            return False
    print("PASS: all outputs present")
    return True


def _reset_artifact_outputs(output_dir: Path) -> None:
    """Remove prior db/chroma artifacts before a full rebuild."""
    import shutil

    db_path = output_dir / "dc42.db"
    chroma_path = output_dir / "chroma_db"
    if db_path.is_file():
        db_path.unlink()
    if chroma_path.is_dir():
        shutil.rmtree(chroma_path)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Build DC42 knowledge base")
    parser.add_argument("--source", type=Path, help="DC42 txt source tree")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="Skip LLM enrichment; build dc42.db + chroma_db from extracted code only",
    )
    parser.add_argument(
        "--staging",
        type=Path,
        help="Load pre-extracted code from staging/ (manifest.jsonl + *.py)",
    )
    args = parser.parse_args()

    if not args.staging and args.source is None:
        parser.error("--source is required unless --staging is provided")

    args.output.mkdir(parents=True, exist_ok=True)

    if args.staging:
        enriched = load_staging_extracts(args.staging)
        _reset_artifact_outputs(args.output)
        stats = compute_parameter_stats(enriched, args.output)
        chunk_and_embed(enriched=enriched, stats=stats, output_dir=args.output)
        validate(args.output)
        print(f"Built artifacts from staging for {len(enriched)} strategies")
    elif args.no_llm:
        manifest = ingest(source_dir=args.source, output_dir=args.output)
        results = extract_code(manifest=manifest, source_dir=args.source, output_dir=args.output)
        ok_count = sum(1 for r in results if r["code_status"] == "ok")
        print(f"Ingested {len(manifest)} strategies, {ok_count} with code")
        enriched = build_without_llm(results)
        _reset_artifact_outputs(args.output)
        stats = compute_parameter_stats(enriched, args.output)
        chunk_and_embed(enriched=enriched, stats=stats, output_dir=args.output)
        validate(args.output)
        print(f"Built artifacts for {len(enriched)} strategies")
    else:
        manifest = ingest(source_dir=args.source, output_dir=args.output)
        results = extract_code(manifest=manifest, source_dir=args.source, output_dir=args.output)
        ok_count = sum(1 for r in results if r["code_status"] == "ok")
        print(f"Ingested {len(manifest)} strategies, {ok_count} with code")
