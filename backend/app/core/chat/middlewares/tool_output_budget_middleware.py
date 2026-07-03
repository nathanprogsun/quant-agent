"""Middleware that enforces a per-result budget on tool outputs.

Oversized ``ToolMessage`` results are persisted to a configured output
directory and replaced with a compact head + tail preview containing a
file reference. When disk persistence is unavailable (the directory cannot
be created or written), the middleware falls back to head + tail truncation
in memory so the model context is never blown up by a single large tool
return.

This is the resilience layer for the jq_kb retrieval tools: a single
``search_jq_*`` call can return up to 5 chunks x 2500-3500 chars of full
text. Left unbounded, those results inflate the next model-call prompt,
slow the second-turn TTFT, and risk pushing the context window over the
limit. The middleware caps each text result at ``max_chars`` and spills
the rest to disk, keeping the prompt lean.

Non-string content (multimodal blocks, structured payloads) bypasses the
budget: the head + tail preview only makes sense for text, and truncating
arbitrary block lists would corrupt downstream consumers.

Ported from deer-flow ``tool_output_budget_middleware.py`` adapted to
quant-agent's filesystem layout (a local output directory instead of a
sandbox virtual path) and ``run_in_pool`` offloading for the async path.
"""

from __future__ import annotations

import logging
import os
import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, override

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import ToolMessage
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.types import Command

from app.util.asyncio_util.adapter import run_in_pool

logger = logging.getLogger(__name__)

# Default per-result character budget: ~12KB is enough for a usable preview
# of most jq_kb hits while keeping a 5-tool-call turn under ~60KB of context.
DEFAULT_MAX_CHARS = 12_000

# Default output directory. Mirrors the value hardcoded in
# ``Settings.tool_output_dir`` so the standalone middleware (used directly in
# unit tests with an explicit ``output_dir``) keeps a sensible fallback
# without requiring Settings to be loaded. The Settings default is the
# source of truth for the wired agent; update both together.
DEFAULT_OUTPUT_DIR = "data/tool_outputs"


# Split between head and tail of the preview (each gets a quarter of
# max_chars, leaving room for the truncation + file-ref footer). Bounded
# to a minimum of 200 so very small budgets still produce usable previews.
def _preview_half(max_chars: int) -> int:
    return max(max_chars // 4, 200)


# Marker that distinguishes a preview from the original full text so the
# model knows to read the file when it needs the rest.
_PREVIEW_MARKER = "[tool output externalised — full content saved to file]"


def _sanitize_tool_name(name: str) -> str:
    """Strip path separators and traversal components from a tool name."""
    base = os.path.basename(name)
    safe = base.replace("..", "").replace("/", "_").replace("\\", "_")
    return safe or "unknown"


def _build_externalized_filename(tool_name: str) -> str:
    """Build the on-disk filename for an externalized tool output."""
    safe_name = _sanitize_tool_name(tool_name)
    short_id = uuid.uuid4().hex[:12]
    return f"{safe_name}-{short_id}.txt"


def _write_to_disk(output_dir: Path, filename: str, content: str) -> Path | None:
    """Write *content* to ``output_dir/filename`` and return the path.

    Returns ``None`` if the disk write fails for any reason (permission,
    missing parent directory that cannot be created, OS error). The caller
    treats ``None`` as "fall back to in-memory truncation".
    """
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / filename
        path.write_text(content, encoding="utf-8")
        return path
    except OSError:
        logger.warning(
            "tool output externalisation to %s failed; using in-memory truncation", output_dir
        )
        return None


def _head_tail_preview(content: str, *, max_chars: int, file_ref: str | None) -> tuple[str, bool]:
    """Build a head + tail preview of *content* capped at roughly *max_chars*.

    Returns ``(preview, externalized)``. ``externalized`` is True whenever
    the original content exceeded ``max_chars`` (regardless of whether a
    file reference is available). When *file_ref* is None the preview omits
    the file-reference footer (in-memory truncation fallback).
    """
    if len(content) <= max_chars:
        return content, False

    half = _preview_half(max_chars)
    head = content[:half]
    tail = content[-half:]

    if file_ref is not None:
        footer = (
            f"\n\n{_PREVIEW_MARKER}\n"
            f"File: {file_ref}\n"
            "Use the read_file tool with this path to view the full output."
        )
    else:
        footer = f"\n\n...[truncated {len(content) - 2 * half} chars]..."

    return f"{head}\n[...truncated...]\n{tail}{footer}", True


class ToolOutputBudgetMiddleware(AgentMiddleware[AgentState]):
    """Cap each ``ToolMessage`` text result; spill the rest to disk.

    Args:
        output_dir: Directory used to persist oversized tool outputs. The
            directory is created lazily on first externalisation; when it
            cannot be created or written, the middleware falls back to
            in-memory head + tail truncation.
        max_chars: Per-result character budget. Results at or below this
            length pass through unchanged. Defaults to ``DEFAULT_MAX_CHARS``.
    """

    def __init__(
        self,
        output_dir: str | os.PathLike[str] = DEFAULT_OUTPUT_DIR,
        max_chars: int = DEFAULT_MAX_CHARS,
    ) -> None:
        self._output_dir = Path(output_dir)
        self._max_chars = max_chars

    # -- shared transformation ------------------------------------------------

    def _maybe_externalize(self, result: ToolMessage | Command[Any]) -> ToolMessage | Command[Any]:
        """Replace an oversized ToolMessage body with a head + tail preview.

        ``Command`` results and non-string-content messages pass through
        unchanged: ``Command`` carries LangGraph control flow rather than
        user-facing text, and truncating multimodal block lists would
        corrupt downstream consumers.
        """
        if not isinstance(result, ToolMessage):
            return result

        content = result.content
        if not isinstance(content, str):
            # Non-string content (multimodal blocks, structured payloads)
            # bypasses the budget: the head + tail preview only makes sense
            # for text, and truncating arbitrary block lists would corrupt
            # downstream consumers.
            return result

        if len(content) <= self._max_chars:
            return result

        tool_name = result.name or "unknown"
        filename = _build_externalized_filename(tool_name)
        file_path = _write_to_disk(self._output_dir, filename, content)
        file_ref = str(file_path) if file_path is not None else None

        preview, _externalized = _head_tail_preview(
            content, max_chars=self._max_chars, file_ref=file_ref
        )
        return ToolMessage(
            content=preview,
            tool_call_id=result.tool_call_id,
            name=result.name,
            status=result.status,
            additional_kwargs=dict(result.additional_kwargs or {}),
        )

    # -- hooks ----------------------------------------------------------------

    @override
    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolMessage | Command[Any]],
    ) -> ToolMessage | Command[Any]:
        result = handler(request)
        return self._maybe_externalize(result)

    @override
    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command[Any]]],
    ) -> ToolMessage | Command[Any]:
        result = await handler(request)
        if not isinstance(result, ToolMessage) or not isinstance(result.content, str):
            return result
        if len(result.content) <= self._max_chars:
            return result
        # Offload the disk write + preview build to a worker thread so a
        # large tool output does not block the event loop.
        return await run_in_pool(self._maybe_externalize, None, result)
