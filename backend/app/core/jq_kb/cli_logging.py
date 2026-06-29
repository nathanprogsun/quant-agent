"""CLI logging helpers for jq_kb scripts (ingest / eval pipeline)."""

from __future__ import annotations

import logging
import time

# Noisy third-party loggers during batch embedding / HTTP calls.
_QUIET_LOGGERS = (
    "httpx",
    "httpcore",
    "urllib3",
    "llama_index",
    "llama_index.core",
    "llama_index.core.indices.utils",
    "llama_index.vector_stores.chroma",
    "chromadb",
    "openai",
)


def configure_cli_logging(*, level: int = logging.INFO) -> None:
    """Use readable stdout logs; silence per-request HTTP noise."""
    logging.basicConfig(
        level=level,
        format="%(levelname)s %(message)s",
        force=True,
    )
    for name in _QUIET_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)


class InferenceProgress:
    """Throttled progress for jq_kb embedding / rerank during CLI ingest."""

    def __init__(self) -> None:
        self.label = "jq_kb"
        self.embed_calls = 0
        self.embed_texts = 0
        self.rerank_calls = 0
        self._last_log = 0.0

    def reset(self, label: str) -> None:
        if self.embed_calls or self.rerank_calls:
            self.flush()
        self.label = label
        self.embed_calls = 0
        self.embed_texts = 0
        self.rerank_calls = 0
        self._last_log = time.monotonic()

    def record_embed(self, n: int) -> None:
        prev_bucket = self.embed_texts // 500
        self.embed_calls += 1
        self.embed_texts += n
        new_bucket = self.embed_texts // 500
        now = time.monotonic()
        first = self.embed_calls == 1
        crossed = new_bucket > prev_bucket
        elapsed = now - self._last_log >= 15.0
        if not (first or crossed or elapsed):
            return
        self._last_log = now
        logging.getLogger(__name__).info(
            "%s embedding… %d texts (%d API calls)",
            self.label,
            self.embed_texts,
            self.embed_calls,
        )

    def record_rerank(self, *, doc_count: int) -> None:
        self.rerank_calls += 1
        logging.getLogger(__name__).debug(
            "%s rerank: %d docs (call #%d)",
            self.label,
            doc_count,
            self.rerank_calls,
        )

    def flush(self) -> None:
        if not self.embed_calls and not self.rerank_calls:
            return
        logging.getLogger(__name__).info(
            "%s inference done: %d texts embedded (%d API calls), %d reranks",
            self.label,
            self.embed_texts,
            self.embed_calls,
            self.rerank_calls,
        )


_progress = InferenceProgress()


def reset_inference_progress(label: str) -> None:
    _progress.reset(label)


def record_embed_batch(n: int) -> None:
    _progress.record_embed(n)


def record_rerank_call(*, doc_count: int) -> None:
    _progress.record_rerank(doc_count=doc_count)


def flush_inference_progress() -> None:
    _progress.flush()
