"""Merge Chrome MCP browser crawl (sessionStorage export) into full.json.

After browser crawl completes, export from Chrome console::

    copy(JSON.stringify(JSON.parse(sessionStorage.getItem('__JQ_DICT__'))))

Save to backend/data/jq_dict/raw/browser_export.json, then::

    uv run python scripts/merge_browser_crawl.py
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.jq_kb.paths import JQ_DICT_RAW_DIR

BROWSER_EXPORT = JQ_DICT_RAW_DIR / "browser_export.json"
FULL_JSON = JQ_DICT_RAW_DIR / "full.json"


def _dedupe(entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    out: list[dict[str, Any]] = []
    for e in entities:
        key = (e.get("type", ""), e.get("code", ""))
        if not e.get("code") or key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "code": e["code"],
                "name": e.get("name", ""),
                "type": e.get("type", "field"),
                "source_description": e.get("source_description", ""),
                "source_url": e.get("source_url", ""),
                **({"unit": e["unit"]} if e.get("unit") else {}),
                **({"sample": e["sample"]} if e.get("sample") else {}),
            }
        )
    return out


def merge_browser_export(export_path: Path = BROWSER_EXPORT) -> dict[str, Any]:
    if not export_path.is_file():
        raise FileNotFoundError(export_path)
    browser_entities = json.loads(export_path.read_text(encoding="utf-8"))
    if isinstance(browser_entities, dict) and "entities" in browser_entities:
        browser_entities = browser_entities["entities"]

    httpx_entities: list[dict[str, Any]] = []
    if FULL_JSON.is_file():
        httpx_entities = json.loads(FULL_JSON.read_text()).get("entities", [])

    merged = _dedupe([*httpx_entities, *browser_entities])
    payload: dict[str, Any] = {
        "version": f"browser-{datetime.now(UTC).date().isoformat()}",
        "source": "Chrome MCP crawl (logged-in) + httpx fallback",
        "crawl_at": datetime.now(UTC).isoformat(),
        "count": len(merged),
        "entities": merged,
    }
    FULL_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def main() -> None:
    payload = merge_browser_export()
    counts = Counter(e["type"] for e in payload["entities"])
    print(f"Merged {FULL_JSON} ({payload['count']} entities)")
    for t, n in sorted(counts.items()):
        print(f"  {t}: {n}")


if __name__ == "__main__":
    main()
