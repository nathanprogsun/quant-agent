"""Chunk JoinQuant data-dictionary raw JSON into JqDictChunk objects.

Each entity (industry / concept / index / field / suffix) becomes one atomic
chunk.  No LLM summary — ``source_description`` comes from the crawl table.
"""

from __future__ import annotations

import re
from typing import Any

from app.core.jq_kb.schemas import DictType, JqDictChunk

BASE_URL = "https://www.joinquant.com/data"

# Static suffix list (PLAN §3.2 — not crawled).
STATIC_SUFFIXES: list[dict[str, str]] = [
    {"code": ".XSHG", "name": "上海证券交易所", "type": "suffix"},
    {"code": ".XSHE", "name": "深圳证券交易所", "type": "suffix"},
    {"code": ".XHKG", "name": "香港交易所", "type": "suffix"},
    {"code": ".IB", "name": "银行间债券", "type": "suffix"},
    {"code": ".OF", "name": "公募基金", "type": "suffix"},
    {"code": ".CCFX", "name": "中金所期货", "type": "suffix"},
]


def _safe_id(dict_type: str, code: str) -> str:
    safe_code = re.sub(r"[^\w.\-]", "_", code)
    return f"dict::{dict_type}::{safe_code}"


def _build_header(dict_type: DictType, code: str, name: str) -> str:
    return f"[jq_dict | type={dict_type.value} | code={code}]\n名称: {name}"


def _format_content(record: dict[str, Any]) -> str:
    lines: list[str] = [
        f"类型: {record.get('type', '')}",
        f"代码: {record.get('code', '')}",
        f"名称: {record.get('name', '')}",
    ]
    desc = (record.get("source_description") or record.get("description") or "").strip()
    if desc:
        lines.append(f"说明: {desc}")
    unit = record.get("unit")
    if unit:
        lines.append(f"单位: {unit}")
    sample = record.get("sample")
    if sample:
        lines.append(f"样例: {sample}")
    if record.get("parent_code"):
        lines.append(f"父级: {record['parent_code']}")
    return "\n".join(lines)


def chunk_jq_dict_record(record: dict[str, Any]) -> JqDictChunk | None:
    code = str(record.get("code", "")).strip()
    name = str(record.get("name", "")).strip()
    raw_type = str(record.get("type", "")).strip().lower()
    if not code or not name or not raw_type:
        return None
    try:
        dict_type = DictType(raw_type)
    except ValueError:
        return None

    source_url = str(record.get("source_url") or BASE_URL)
    source_description = str(
        record.get("source_description") or record.get("description") or ""
    ).strip()
    content = _format_content(record)
    header = _build_header(dict_type, code, name)

    return JqDictChunk(
        id=_safe_id(dict_type.value, code),
        code=code,
        name=name,
        dict_type=dict_type,
        unit=record.get("unit") or None,
        sample=str(record.get("sample")) if record.get("sample") is not None else None,
        source_description=source_description,
        source_url=source_url,
        parent_code=record.get("parent_code") or None,
        content=content,
        contextual_content=f"{header}\n\n{content}",
    )


def chunk_jq_dict_records(records: list[dict[str, Any]]) -> list[JqDictChunk]:
    chunks: list[JqDictChunk] = []
    for record in records:
        chunk = chunk_jq_dict_record(record)
        if chunk is not None:
            chunks.append(chunk)
    return chunks


def static_suffix_records() -> list[dict[str, str]]:
    return list(STATIC_SUFFIXES)
