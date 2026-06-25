"""Parse local JoinQuant strategy .txt files into structured posts."""

from __future__ import annotations

import hashlib
import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

HEADER_RE = re.compile(
    r"#\s*克隆自聚宽文章[:：]\s*(?P<url>https?://\S+)\s*\n"
    r"#\s*标题[:：]\s*(?P<title>.+?)\s*\n"
    r"#\s*作者[:：]\s*(?P<author>.+?)\s*(?:\n|$)",
    re.MULTILINE,
)
LEGAL_NOTE_RE = re.compile(r"该策略由聚宽用户分享,?仅供学习交流使用\.?")
ENCODING_CANDIDATES = ("utf-8", "gbk", "gb2312", "latin-1")


def read_text_robust(filepath: Path) -> str:
    raw = filepath.read_bytes()
    for enc in ENCODING_CANDIDATES:
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", errors="replace")


def stable_hash(s: str) -> int:
    return int(hashlib.md5(s.encode()).hexdigest()[:8], 16)


def extract_post_id_from_url(url: str) -> int | None:
    m = re.search(r"/post/(\d+)", url)
    return int(m.group(1)) if m else None


def parse_strategy_txt(filepath: Path) -> dict[str, Any]:
    text = read_text_robust(filepath)
    text = text.replace("\r\n", "\n")
    text = LEGAL_NOTE_RE.sub("", text).strip()
    is_notebook = "# In[" in text or "#In[" in text

    m = HEADER_RE.search(text)
    if m:
        url = m.group("url")
        post_id = extract_post_id_from_url(url) or stable_hash(filepath.name)
        title = m.group("title").strip()
        author = m.group("author").strip()
        code = text[m.end() :].strip()
        status = "ok"
    else:
        clean_name = re.sub(r"^[\d\s.]+", "", filepath.stem)
        title = clean_name
        author = "unknown"
        url = None
        post_id = stable_hash(filepath.name) % 100000
        code = text.strip()
        status = "no_header"

    year_match = re.search(r"(\d{4})年度", str(filepath))
    year = int(year_match.group(1)) if year_match else 2023
    if "(1)" in filepath.name or "(2)" in filepath.name:
        status = "duplicate"

    return {
        "post_id": post_id,
        "year": year,
        "title": title,
        "author": author,
        "source_url": url,
        "code": code,
        "is_notebook": is_notebook,
        "parse_status": status,
        "source_file": str(filepath),
    }


def load_all_strategies(
    base_dir: Path,
    *,
    skip_duplicates: bool = True,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    seen_titles: set[str] = set()
    seen_post_ids: dict[int, str] = {}
    stats: dict[str, int] = {}

    for year_dir in sorted(base_dir.iterdir()):
        if not year_dir.is_dir() or "年度" not in year_dir.name:
            continue
        for f in sorted(year_dir.glob("*.txt")):
            data = parse_strategy_txt(f)
            if skip_duplicates and data["parse_status"] == "duplicate":
                stats["duplicate"] = stats.get("duplicate", 0) + 1
                continue
            title_key = f"{data['title']}_{data['year']}"
            if title_key in seen_titles:
                stats["duplicate"] = stats.get("duplicate", 0) + 1
                continue
            seen_titles.add(title_key)

            pid = int(data["post_id"])
            if pid in seen_post_ids and seen_post_ids[pid] != data["title"]:
                data["post_id"] = stable_hash(str(f))
                data["parse_status"] = "post_id_collision"
                stats["post_id_collision"] = stats.get("post_id_collision", 0) + 1
                logger.warning(
                    "post_id %s reused by %r; reassigned to %s for %s",
                    pid,
                    seen_post_ids[pid],
                    data["post_id"],
                    f.name,
                )
            else:
                seen_post_ids[pid] = str(data["title"])

            results.append(data)
            stats[data["parse_status"]] = stats.get(data["parse_status"], 0) + 1

    logger.info("Loaded %d strategies from %s stats=%s", len(results), base_dir, stats)
    return results
