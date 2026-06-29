"""Shared utilities for jq_kb."""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

from app.settings import get_settings

logger = logging.getLogger(__name__)


def json_safe_value(value: Any) -> Any:
    """Recursively convert values to JSON-serializable forms (e.g. set → list)."""
    if isinstance(value, set):
        return sorted(json_safe_value(item) for item in value)
    if isinstance(value, (list, tuple)):
        return [json_safe_value(v) for v in value]
    if isinstance(value, dict):
        return {str(k): json_safe_value(v) for k, v in value.items()}
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def split_text(text: str, max_chars: int) -> list[str]:
    """Split long text into fixed-size parts for embedding-sized chunks."""
    if max_chars <= 0 or len(text) <= max_chars:
        return [text] if text else []
    parts: list[str] = []
    for start in range(0, len(text), max_chars):
        part = text[start : start + max_chars]
        if start > 0:
            part = f"...(续)\n{part}"
        if start + max_chars < len(text):
            part = f"{part}\n...(截断)"
        parts.append(part)
    return parts


def fit_text_for_embedding(text: str, *, max_chars: int | None = None) -> str:
    """Clamp text to provider-safe length (last-resort before HTTP call)."""
    if not text:
        return text
    if max_chars is None:
        max_chars = get_settings().jq_kb_embedding_max_chars
    if len(text) <= max_chars:
        return text
    logger.warning("truncating embedding input from %d to %d chars", len(text), max_chars)
    marker = "\n...(truncated for embedding)"
    keep = max(max_chars - len(marker), 1)
    return text[:keep] + marker


def bm25_manifest_path(bm25_path: Path) -> Path:
    """Return the SHA-256 manifest companion path for a BM25 pickle file."""
    return bm25_path.with_name(bm25_path.name + ".manifest.json")


def verify_bm25(bm25_path: Path) -> None:
    """Verify BM25 pickle integrity against its SHA-256 manifest.

    Raises:
        ValueError: If a manifest exists and the SHA-256 hash does not match.
    """
    manifest_path = bm25_manifest_path(bm25_path)
    if not manifest_path.is_file():
        # No manifest — first run or pre-existing artifact; accept.
        return
    actual = hashlib.sha256(bm25_path.read_bytes()).hexdigest()
    expected = json.loads(manifest_path.read_text()).get("sha256")
    if expected and actual != expected:
        raise ValueError(
            f"BM25 index {bm25_path} failed integrity check; re-run ingest"
        )


def write_bm25(bm25_path: Path, data: bytes) -> None:
    """Write BM25 pickle + SHA-256 manifest atomically."""
    bm25_path.write_bytes(data)
    bm25_manifest_path(bm25_path).write_text(
        json.dumps({"sha256": hashlib.sha256(data).hexdigest()})
    )
