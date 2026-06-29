"""HTTP client for jq_kb text embedding (OpenAI-compatible ``/embeddings``)."""

from __future__ import annotations

import logging
import time
from typing import Any, cast

import httpx

from app.core.jq_kb.cli_logging import record_embed_batch
from app.core.jq_kb.errors import InferenceConfigError
from app.core.jq_kb.http_client import get_http_client
from app.core.jq_kb.utils import fit_text_for_embedding
from app.settings import get_settings

logger = logging.getLogger(__name__)


def _embedding_settings() -> tuple[str, str, str]:
    settings = get_settings()
    api_key = settings.jq_kb_embedding_api_key.get_secret_value().strip()
    base_url = settings.jq_kb_embedding_base_url.rstrip("/")
    model = settings.jq_kb_embedding_model.strip()
    if not api_key or not base_url or not model:
        raise InferenceConfigError(
            "Set JQKB_EMBEDDING_API_KEY, JQKB_EMBEDDING_BASE_URL, JQKB_EMBEDDING_MODEL "
            "(or legacy OPENAI_EMBEDDING_* env vars) in backend/.env"
        )
    return api_key, base_url, model


def _post_embeddings(
    *,
    base_url: str,
    api_key: str,
    payload: dict[str, Any],
    max_retries: int,
) -> dict[str, Any]:
    """Single POST with retry on transient status / network errors."""
    last_error: Exception | None = None
    for attempt in range(max_retries):
        try:
            response = get_http_client().post(
                f"{base_url}/embeddings",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
        except (httpx.RemoteProtocolError, httpx.ConnectError, httpx.ReadTimeout, httpx.WriteTimeout) as exc:
            last_error = exc
            wait = min(2**attempt, 30)
            logger.warning(
                "embedding network error %s, retry in %ds (attempt %d/%d)",
                exc.__class__.__name__,
                wait,
                attempt + 1,
                max_retries,
            )
            time.sleep(wait)
            continue
        if response.status_code == 400:
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                raise RuntimeError(f"embedding rejected by provider: {response.text[:500]}") from exc
        if response.status_code == 429 or response.status_code >= 500:
            wait = min(2**attempt, 30)
            logger.warning(
                "embedding HTTP %d, retry in %ds (attempt %d/%d)",
                response.status_code,
                wait,
                attempt + 1,
                max_retries,
            )
            time.sleep(wait)
            continue
        response.raise_for_status()
        return cast(dict[str, Any], response.json())
    raise RuntimeError(f"embedding failed after {max_retries} attempts") from last_error


def _split_batches(items: list[Any], size: int) -> list[list[Any]]:
    if size <= 0 or size >= len(items):
        return [items]
    return [items[i : i + size] for i in range(0, len(items), size)]


def embed_texts(
    texts: list[str],
    *,
    max_retries: int = 5,
    batch_size: int = 8,
) -> list[list[float]]:
    """Embed texts via configured provider ``POST {base_url}/embeddings``.

    The provider may drop long batches (peer closed connection); we chunk
    each call into ``batch_size``-sized sub-batches and re-try the failing
    sub-batch independently so a transient blip on one batch doesn't blow
    up the whole ingest.
    """
    if not texts:
        return []
    texts = [fit_text_for_embedding(t) for t in texts]
    api_key, base_url, model = _embedding_settings()

    vectors: list[list[float]] = []
    for batch in _split_batches(texts, batch_size):
        payload: dict[str, Any] = {
            "model": model,
            "input": batch if len(batch) > 1 else batch[0],
        }
        body = _post_embeddings(
            base_url=base_url,
            api_key=api_key,
            payload=payload,
            max_retries=max_retries,
        )
        if "data" not in body:
            raise RuntimeError(f"missing 'data' in response: {body!r:.500}")
        data = sorted(body["data"], key=lambda row: row["index"])
        vectors.extend(row["embedding"] for row in data)
        record_embed_batch(len(data))
    return vectors
