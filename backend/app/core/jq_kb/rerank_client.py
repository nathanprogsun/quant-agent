"""HTTP client for jq_kb cross-encoder reranking."""

from __future__ import annotations

from typing import Any, cast

from app.core.jq_kb.cli_logging import record_rerank_call
from app.core.jq_kb.errors import InferenceConfigError
from app.core.jq_kb.http_client import get_http_client
from app.settings import get_settings


def _rerank_settings() -> tuple[str, str, str]:
    settings = get_settings()
    api_key = settings.jq_kb_rerank_api_key.get_secret_value().strip()
    base_url = settings.jq_kb_rerank_base_url.rstrip("/")
    model = settings.jq_kb_rerank_model.strip()
    if not api_key or not base_url or not model:
        raise InferenceConfigError(
            "Set JQKB_RERANK_API_KEY, JQKB_RERANK_BASE_URL, JQKB_RERANK_MODEL "
            "(or legacy OPENAI_RERANK_* env vars) in backend/.env"
        )
    return api_key, base_url, model


def rerank_documents(*, query: str, documents: list[str], top_n: int) -> list[dict[str, Any]]:
    """Rerank documents via configured provider endpoint (full URL from settings)."""
    if not documents:
        return []
    api_key, base_url, model = _rerank_settings()
    response = get_http_client().post(
        base_url,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": model,
            "query": query,
            "documents": documents,
            "top_n": min(top_n, len(documents)),
        },
    )
    response.raise_for_status()
    record_rerank_call(doc_count=len(documents))
    return cast(list[dict[str, Any]], response.json()["results"])
