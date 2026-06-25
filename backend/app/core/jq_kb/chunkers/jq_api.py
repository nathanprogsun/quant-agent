"""Chunk JoinQuant API raw JSON into JqApiChunk objects.

Handles both hand-authored pilot.json (rich params/returns/examples) and
Chrome-MCP-crawled full.json (sparse params, dense signatures). Splitting
rules:

- Functions with ``a/b/c`` composite names (e.g. ``run_daily/run_weekly/run_monthly``)
  are split into one chunk per variant so BM25 matches the exact function.
- IDs are namespaced by module + sanitized function name to avoid upsert
  collisions across modules.
- env is inferred from notes + ♠ markers, falling back to ALL when neither
  pattern is present (most JQ strategy APIs run in all environments).
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

from app.core.jq_kb.schemas import JqApiChunk, JqApiEnvConstraint, Library, Source

BASE_URL = "https://www.joinquant.com/help/api/help"


def _parse_env(text: str) -> list[JqApiEnvConstraint]:
    """Infer env constraints from notes/♠ markers in JQ doc."""
    env: list[JqApiEnvConstraint] = []
    if "研究" in text or "research" in text.lower():
        env.append(JqApiEnvConstraint.RESEARCH)
    if "回测" in text or "backtest" in text.lower():
        env.append(JqApiEnvConstraint.BACKTEST)
    if "模拟" in text or "paper" in text.lower():
        env.append(JqApiEnvConstraint.PAPER_TRADING)
    if "实盘" in text or "live" in text.lower() or "trading" in text.lower():
        env.append(JqApiEnvConstraint.TRADING)
    return env or [JqApiEnvConstraint.ALL]


def _build_contextual_header(
    module: str,
    env: list[JqApiEnvConstraint],
    function_name: str,
) -> str:
    env_text = ", ".join(e.value for e in env)
    return f"[jq_api | module={module} | env={env_text}]\n函数: {function_name}"


def _format_content(record: dict[str, Any], function_name: str | None = None) -> str:
    """Format the BM25-indexed content (rich Chinese context for matching).

    Adds description (Chinese) prominently so user queries in Chinese can hit.
    """
    fn = function_name or record.get("function_name", "")
    lines: list[str] = []

    desc = record.get("description", "").strip()
    if desc:
        lines.append(f"描述: {desc}")
    lines.append(f"函数: {fn}")
    lines.append(f"签名: {record.get('signature', '')}")

    params = record.get("params") or []
    if params:
        lines.append("参数:")
        for p in params:
            lines.append(
                f"  - {p.get('name', '')} ({p.get('type', '')}, default={p.get('default', '-')}) "
                f"{p.get('description', '')}"
            )

    if record.get("returns"):
        lines.append(f"返回值: {record['returns']}")

    for ex in record.get("examples") or []:
        lines.append(f"示例:\n{ex}")

    if record.get("notes"):
        lines.append(f"说明: {record['notes']}")

    return "\n".join(lines)


def _split_composite_name(name: str) -> list[str]:
    """Split ``a/b/c`` style names so each variant becomes its own chunk."""
    if "/" not in name:
        return [name]
    parts = [p.strip() for p in name.split("/") if p.strip()]
    return parts if len(parts) > 1 else [name]


def _safe_id(module: str, function_name: str, idx: int = 0) -> str:
    """Stable id: ``jq_api::{module}::{fn_hash}::{idx}`` (avoids : in fn name)."""
    safe_module = re.sub(r"[^\w]", "_", module or "unknown")
    fn_hash = hashlib.md5(function_name.encode("utf-8")).hexdigest()[:8]
    return f"jq_api::{safe_module}::{fn_hash}::{idx}"


def chunk_jq_api_record(record: dict[str, Any]) -> list[JqApiChunk]:
    """Convert one raw API record dict to 1+ JqApiChunks.

    Composite names (e.g. ``run_daily/run_weekly/run_monthly``) yield
    multiple chunks — one per variant — sharing the same signature/params
    but distinct ids and function_names.
    """
    raw_name = record.get("function_name", "").strip()
    if not raw_name:
        return []

    module = record.get("module", "")
    signature = record.get("signature") or f"{raw_name}(...)"
    notes = record.get("notes", "")
    env_text = record.get("env_text", "")
    description = record.get("description", "")
    env = _parse_env(notes + env_text + description)
    content = _format_content(record)
    contextual_header = _build_contextual_header(module, env, raw_name)
    source_url = record.get("source_url") or BASE_URL

    # Split composite names — produce 1 chunk per variant
    variants = _split_composite_name(raw_name)
    chunks: list[JqApiChunk] = []
    for idx, variant in enumerate(variants):
        chunks.append(
            JqApiChunk(
                id=_safe_id(module, variant, idx),
                library=Library.JQ_API,
                source=Source.JQ_OFFICIAL_DOC,
                function_name=variant,
                module=module,
                signature=signature,
                params=list(record.get("params") or []),
                returns=str(record.get("returns") or ""),
                env=env,
                source_url=source_url,
                content=content,
                contextual_content=f"{contextual_header}\n\n{content}",
                examples=list(record.get("examples") or []),
            )
        )
    return chunks


def chunk_jq_api_records(records: list[dict[str, Any]]) -> list[JqApiChunk]:
    """Convert a list of raw API records to flat chunk list."""
    chunks: list[JqApiChunk] = []
    for r in records:
        chunks.extend(chunk_jq_api_record(r))
    return chunks


def infer_function_name(text: str) -> str | None:
    m = re.search(r"\b(get|set|order|create|run|history|attribute_history|normalize|log)[_\w]*", text)
    return m.group(0) if m else None
