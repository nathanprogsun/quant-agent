"""Crawl JoinQuant data dictionary pages into raw/full.json.

Sources (public HTML, no login required):
- https://www.joinquant.com/help/api/plateData   — industry / concept tables
- https://www.joinquant.com/data/dict/indexData  — index list (~600)
- https://www.joinquant.com/help/api/help        — field tables (get_price etc.)

Usage::

    cd backend
    uv run python scripts/crawl_jq_dict.py
    uv run python scripts/ingest_jq_dict.py --reset
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

import httpx

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.jq_kb.paths import JQ_DICT_RAW_DIR

PLATE_URL = "https://www.joinquant.com/help/api/plateData"
INDEX_URL = "https://www.joinquant.com/data/dict/indexData"
HELP_URL = "https://www.joinquant.com/help/api/help"
OUTPUT_PATH = JQ_DICT_RAW_DIR / "full.json"

HEADERS = {
    "User-Agent": "quant-agent-jq-dict-crawler/1.0",
    "Accept-Language": "zh-CN,zh;q=0.9",
}


class _TableCollector(HTMLParser):
    """Collect HTML tables as list[list[str]] cell matrices."""

    def __init__(self) -> None:
        super().__init__()
        self.tables: list[list[list[str]]] = []
        self._in_table = False
        self._in_row = False
        self._in_cell = False
        self._cur_table: list[list[str]] = []
        self._cur_row: list[str] = []
        self._cell_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "table":
            self._in_table = True
            self._cur_table = []
        elif self._in_table and tag == "tr":
            self._in_row = True
            self._cur_row = []
        elif self._in_row and tag in ("td", "th"):
            self._in_cell = True
            self._cell_parts = []

    def handle_endtag(self, tag: str) -> None:
        if tag in ("td", "th") and self._in_cell:
            self._cur_row.append("".join(self._cell_parts).strip())
            self._in_cell = False
        elif tag == "tr" and self._in_row:
            if any(c.strip() for c in self._cur_row):
                self._cur_table.append(self._cur_row)
            self._in_row = False
        elif tag == "table" and self._in_table:
            if self._cur_table:
                self.tables.append(self._cur_table)
            self._in_table = False

    def handle_data(self, data: str) -> None:
        if self._in_cell:
            self._cell_parts.append(data)


def _fetch_html(client: httpx.Client, url: str) -> str:
    resp = client.get(url, follow_redirects=True, timeout=60.0)
    resp.raise_for_status()
    return resp.text


def _header_index(headers: list[str], *patterns: str) -> int:
    for i, h in enumerate(headers):
        for p in patterns:
            if re.search(p, h, re.I):
                return i
    return -1


def _parse_code_name_tables(
    html: str,
    *,
    default_type: str,
    source_url: str,
    type_from_section: str | None = None,
) -> list[dict[str, Any]]:
    parser = _TableCollector()
    parser.feed(html)
    entities: list[dict[str, Any]] = []
    section = type_from_section or ""

    for table in parser.tables:
        if len(table) < 2:
            continue
        headers = table[0]
        code_idx = _header_index(headers, r"代码", r"code")
        name_idx = _header_index(headers, r"名称", r"name", r"分类")
        if code_idx < 0 or name_idx < 0:
            continue

        dict_type = default_type
        if default_type == "industry" and name_idx == code_idx:
            continue

        for row in table[1:]:
            if len(row) <= max(code_idx, name_idx):
                continue
            code = row[code_idx].strip()
            name = row[name_idx].strip()
            if not code or not name or code in {"代码", "code", "字段名"}:
                continue
            if dict_type == "index" and name_idx != code_idx:
                # indexData: col1 is category label, use as name
                pass
            desc_prefix = f"{section}：" if section else ""
            entities.append(
                {
                    "code": code,
                    "name": name,
                    "type": dict_type,
                    "source_description": f"{desc_prefix}{name}",
                    "source_url": source_url,
                }
            )
    return entities


def _parse_plate_data(html: str) -> list[dict[str, Any]]:
    """plateData has multiple sections; infer type from preceding h-tags via HTML order."""
    entities: list[dict[str, Any]] = []
    parts = re.split(
        r"(<h[1-6][^>]*>.*?</h[1-6]>|<strong[^>]*>.*?</strong>)",
        html,
        flags=re.I | re.S,
    )
    current_section = ""
    for part in parts:
        if re.match(r"^<(h[1-6]|strong)\b", part.strip(), re.I):
            text = re.sub(r"<[^>]+>", "", part).strip()
            if re.match(r"^(证监会|聚宽|申万|概念)", text):
                current_section = text
            continue
        if "<table" not in part.lower():
            continue
        dict_type = "concept" if "概念" in current_section else "industry"
        entities.extend(
            _parse_code_name_tables(
                part,
                default_type=dict_type,
                source_url=PLATE_URL,
                type_from_section=current_section,
            )
        )
    return entities


def _parse_index_data(html: str) -> list[dict[str, Any]]:
    parser = _TableCollector()
    parser.feed(html)
    entities: list[dict[str, Any]] = []
    for table in parser.tables:
        if len(table) < 2:
            continue
        headers = table[0]
        code_idx = _header_index(headers, r"指数代码", r"代码")
        name_idx = _header_index(headers, r"指数分类", r"名称")
        if code_idx < 0 or name_idx < 0:
            continue
        for row in table[1:]:
            if len(row) <= max(code_idx, name_idx):
                continue
            code = row[code_idx].strip()
            name = row[name_idx].strip()
            if not code or not name:
                continue
            entities.append(
                {
                    "code": code,
                    "name": name,
                    "type": "index",
                    "source_description": f"指数列表：{name}",
                    "source_url": INDEX_URL,
                }
            )
    return entities


def _parse_field_tables(html: str) -> list[dict[str, Any]]:
    """Parse 字段名/含义 tables from the monolithic help page."""
    entities: list[dict[str, Any]] = []
    parts = re.split(r"(<h[1-6][^>]*>.*?</h[1-6]>)", html, flags=re.I | re.S)
    current_section = ""
    for part in parts:
        if re.match(r"<h", part, re.I):
            current_section = re.sub(r"<[^>]+>", "", part).strip()
            continue
        if "<table" not in part.lower():
            continue
        parser = _TableCollector()
        parser.feed(part)
        for table in parser.tables:
            if len(table) < 2:
                continue
            headers = table[0]
            code_idx = _header_index(headers, r"字段名", r"字段", r"code")
            name_idx = _header_index(headers, r"含义", r"说明", r"描述")
            if code_idx < 0 or name_idx < 0:
                continue
            for row in table[1:]:
                if len(row) <= max(code_idx, name_idx):
                    continue
                code = row[code_idx].strip()
                desc = row[name_idx].strip()
                if not code or not desc or code == "字段名":
                    continue
                entities.append(
                    {
                        "code": code,
                        "name": desc,
                        "type": "field",
                        "source_description": f"{current_section}：{desc}" if current_section else desc,
                        "source_url": HELP_URL + "#name:Stock",
                    }
                )
    return entities


def _dedupe_entities(entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep first occurrence per (type, code); fields may repeat across API sections."""
    seen: set[tuple[str, str]] = set()
    out: list[dict[str, Any]] = []
    for e in entities:
        key = (e["type"], e["code"])
        if key in seen:
            continue
        seen.add(key)
        out.append(e)
    return out


def _load_pilot_field_entities() -> list[dict[str, Any]]:
    """Merge hand-authored field rows from pilot.json (help SPA has no static field tables)."""
    pilot_path = JQ_DICT_RAW_DIR / "pilot.json"
    if not pilot_path.is_file():
        return []
    data = json.loads(pilot_path.read_text(encoding="utf-8"))
    return [e for e in data.get("entities", []) if e.get("type") == "field"]


def crawl_jq_dict(*, output: Path = OUTPUT_PATH) -> dict[str, Any]:
    with httpx.Client(headers=HEADERS) as client:
        plate_html = _fetch_html(client, PLATE_URL)
        index_html = _fetch_html(client, INDEX_URL)
        help_html = _fetch_html(client, HELP_URL)

    entities: list[dict[str, Any]] = []
    entities.extend(_parse_plate_data(plate_html))
    entities.extend(_parse_index_data(index_html))
    entities.extend(_parse_field_tables(help_html))
    entities.extend(_load_pilot_field_entities())
    entities = _dedupe_entities(entities)

    payload = {
        "version": f"real-{datetime.now(timezone.utc).date().isoformat()}",
        "source": "joinquant.com/data + help/api/plateData + data/dict/indexData",
        "crawl_at": datetime.now(timezone.utc).isoformat(),
        "count": len(entities),
        "entities": entities,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def main() -> None:
    payload = crawl_jq_dict()
    by_type: dict[str, int] = {}
    for e in payload["entities"]:
        by_type[e["type"]] = by_type.get(e["type"], 0) + 1
    print(f"Wrote {OUTPUT_PATH} ({payload['count']} entities)")
    for t, n in sorted(by_type.items()):
        print(f"  {t}: {n}")


if __name__ == "__main__":
    main()
