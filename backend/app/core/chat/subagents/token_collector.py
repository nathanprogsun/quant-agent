"""Callback handler that captures per-subagent LLM token usage.

Ports deer-flow's subagents/token_collector.py:16-72. Each subagent
execution creates its own collector; usage_metadata from each
``on_llm_end`` callback is recorded with dedup by ``run_id`` so a
re-entrant callback (the same LLM end firing once per chunk for the
same logical call) does not double-count.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult

logger = logging.getLogger(__name__)


def _extract_model_name(response_metadata: Any) -> str | None:
    """Extract ``model_name`` from a LangChain response_metadata dict."""
    if isinstance(response_metadata, Mapping):
        value = response_metadata.get("model_name") or response_metadata.get("model")
        return str(value) if value else None
    return None


class SubagentTokenCollector(BaseCallbackHandler):
    """Lightweight callback handler that collects LLM token usage within a subagent."""

    def __init__(self, caller: str) -> None:
        super().__init__()
        self.caller = caller
        self._records: list[dict[str, Any]] = []
        self._counted_run_ids: set[str] = set()

    def on_llm_end(
        self,
        response: LLMResult,
        *,
        run_id: Any,
        tags: list[str] | None = None,
        **kwargs: Any,
    ) -> None:
        """Capture usage_metadata from generations, dedup'd by run_id."""
        rid = str(run_id)
        if rid in self._counted_run_ids:
            return
        for generation in response.generations:
            for gen in generation:
                if not hasattr(gen, "message"):
                    continue
                usage = getattr(gen.message, "usage_metadata", None)
                usage_dict = dict(usage) if usage else {}
                input_tk = usage_dict.get("input_tokens", 0) or 0
                output_tk = usage_dict.get("output_tokens", 0) or 0
                total_tk = usage_dict.get("total_tokens", 0) or 0
                if total_tk <= 0:
                    total_tk = input_tk + output_tk
                if total_tk <= 0:
                    continue
                response_metadata = getattr(gen.message, "response_metadata", None) or {}
                model_name = _extract_model_name(response_metadata)
                self._counted_run_ids.add(rid)
                self._records.append(
                    {
                        "source_run_id": rid,
                        "caller": self.caller,
                        "model_name": model_name,
                        "input_tokens": input_tk,
                        "output_tokens": output_tk,
                        "total_tokens": total_tk,
                    }
                )
                return

    def snapshot_records(self) -> list[dict[str, Any]]:
        """Return a copy of the accumulated usage records."""
        return list(self._records)
