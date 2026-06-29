"""Shared HTTP client for jq_kb inference APIs."""

from __future__ import annotations

from functools import lru_cache

import httpx


@lru_cache(maxsize=1)
def get_http_client() -> httpx.Client:
    return httpx.Client(timeout=120.0)
