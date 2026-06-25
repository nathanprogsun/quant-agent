"""Query helpers for jq_api.

LlamaIndex's ``QueryFusionRetriever`` already handles LLM-based query
generation internally — this module is for the two things LlamaIndex
doesn't do well for our case:

1. **Exact-match short-circuit**: when the user names a function
   (``get_price``), bypass retrieval and return the single best chunk.
2. **Known-function whitelist**: read from the ingest manifest, used by
   tools.py to validate ``function_name`` arguments before passing to
   the retriever.

For semantic query rewriting / HyDE / multi-query fusion, use
``QueryFusionRetriever(llm=..., num_queries=4)`` directly.
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache

from app.core.jq_kb.paths import JQ_API_MANIFEST_PATH, JQ_DICT_MANIFEST_PATH

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def known_function_names() -> frozenset[str]:
    """Read the whitelist of indexed jq_api function names from manifest.

    Used to:
    - Validate ``function_name`` arguments in tools.py before retrieval
    - Provide fast exact-match shortcut in retriever (cheap fallback before
      LLM query gen runs)
    """
    if not JQ_API_MANIFEST_PATH.is_file():
        return frozenset()
    try:
        data = json.loads(JQ_API_MANIFEST_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.warning("Could not parse manifest %s: %s", JQ_API_MANIFEST_PATH, exc)
        return frozenset()
    names = data.get("function_names") or []
    return frozenset(n for n in names if isinstance(n, str))


def is_known_function(name: str) -> bool:
    """True if ``name`` matches a function ingested into jq_api."""
    return name in known_function_names()


def suggest_function_names(query: str, limit: int = 5) -> list[str]:
    """Return known function names mentioned in ``query`` (substring match).

    Cheap heuristic — no LLM. Useful for the tool wrapper to auto-fill
    ``function_name`` if the user's query obviously names one.
    """
    lower = query.lower()
    found: list[str] = []
    for name in known_function_names():
        if name.lower() in lower and name not in found:
            found.append(name)
        if len(found) >= limit:
            break
    return found


def reset_known_names_cache() -> None:
    """Invalidate the manifest cache (call after re-ingest)."""
    known_function_names.cache_clear()
    known_codes.cache_clear()


@lru_cache(maxsize=1)
def known_codes() -> frozenset[str]:
    """Read indexed jq_dict codes from manifest."""
    if not JQ_DICT_MANIFEST_PATH.is_file():
        return frozenset()
    try:
        data = json.loads(JQ_DICT_MANIFEST_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.warning("Could not parse manifest %s: %s", JQ_DICT_MANIFEST_PATH, exc)
        return frozenset()
    codes = data.get("codes") or []
    return frozenset(c for c in codes if isinstance(c, str))


def is_known_code(name: str) -> bool:
    return name in known_codes()