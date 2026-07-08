"""Tests for ToolOutputBudgetMiddleware.

Verifies that oversized ``ToolMessage`` results are externalised to disk
and replaced with a head + tail preview containing a file reference, while
small results pass through unchanged. When the configured output directory
is unavailable, the middleware falls back to head+tail truncation in memory
so the model context is never blown up by a single large tool return.

This is the second resilience layer for the jq_kb retrieval tools: a single
``search_jq_*`` call can return 5 chunks x 2500-3500 chars of full text,
which inflates the next model-call prompt, slows second-turn TTFT, and
risks pushing the context window over the limit. The middleware caps each
result at ``max_chars`` and spills the rest to disk.
"""

from __future__ import annotations

from pathlib import Path

from langchain_core.messages import ToolMessage
from langgraph.prebuilt.tool_node import ToolCallRequest

from app.core.chat.middlewares.tool_output_budget_middleware import (
    ToolOutputBudgetMiddleware,
    _head_tail_preview,
)


def _request(tool_name: str = "search_jq_api", tool_call_id: str = "call-1") -> ToolCallRequest:
    return ToolCallRequest(
        tool_call={
            "name": tool_name,
            "args": {"query": "x"},
            "id": tool_call_id,
            "type": "tool_call",
        },
        tool=None,  # type: ignore[arg-type]
        state={"messages": []},
        runtime=None,  # type: ignore[arg-type]
    )


class TestHeadTailPreview:
    def test_short_text_passthrough(self) -> None:
        text = "short result"
        preview, externalized = _head_tail_preview(text, max_chars=100, file_ref=None)
        assert preview == text
        assert externalized is False

    def test_long_text_becomes_head_tail_with_file_ref(self) -> None:
        text = "L" * 1000
        preview, externalized = _head_tail_preview(text, max_chars=200, file_ref="/tmp/out.log")
        assert externalized is True
        assert preview.startswith("L")
        assert "/tmp/out.log" in preview
        # head + tail + ellipsis + file-ref block
        assert len(preview) < len(text)

    def test_file_ref_none_falls_back_to_in_memory_truncation(self) -> None:
        text = "L" * 1000
        preview, externalized = _head_tail_preview(text, max_chars=200, file_ref=None)
        assert externalized is True
        assert "/tmp" not in preview  # no file ref block
        assert len(preview) < len(text)


class TestAsyncWrapToolCall:
    async def test_small_tool_message_passes_through(self, tmp_path: Path) -> None:
        mw = ToolOutputBudgetMiddleware(output_dir=str(tmp_path), max_chars=10_000)
        original = ToolMessage(content="small", tool_call_id="call-1", name="t")

        async def handler(req: ToolCallRequest) -> ToolMessage:
            return original

        result = await mw.awrap_tool_call(_request(), handler)
        assert result is original

    async def test_oversize_tool_message_externalised_to_disk(self, tmp_path: Path) -> None:
        mw = ToolOutputBudgetMiddleware(output_dir=str(tmp_path), max_chars=200)
        big_content = "X" * 2000
        original = ToolMessage(content=big_content, tool_call_id="call-1", name="search_jq_api")

        async def handler(req: ToolCallRequest) -> ToolMessage:
            return original

        result = await mw.awrap_tool_call(_request("search_jq_api", "call-1"), handler)
        assert isinstance(result, ToolMessage)
        # The on-disk file should exist.
        files = list(tmp_path.glob("search_jq_api-*.txt"))
        assert len(files) == 1
        assert files[0].read_text() == big_content

        # The replacement content should be much smaller and reference the file.
        new_content = result.content
        assert isinstance(new_content, str)
        assert len(new_content) < len(big_content)
        assert str(files[0]) in new_content

    async def test_oversize_falls_back_to_in_memory_when_dir_missing(self) -> None:
        # Point at a path that cannot be created (read-only parent / invalid).
        mw = ToolOutputBudgetMiddleware(output_dir="/nonexistent-root/outputs", max_chars=200)
        big_content = "Y" * 2000
        original = ToolMessage(content=big_content, tool_call_id="call-1", name="t")

        async def handler(req: ToolCallRequest) -> ToolMessage:
            return original

        result = await mw.awrap_tool_call(_request(), handler)
        assert isinstance(result, ToolMessage)
        new_content = result.content
        assert isinstance(new_content, str)
        assert len(new_content) < len(big_content)
        # No file ref block because externalisation failed.
        assert "/nonexistent-root" not in new_content

    async def test_non_string_content_passes_through(self, tmp_path: Path) -> None:
        mw = ToolOutputBudgetMiddleware(output_dir=str(tmp_path), max_chars=10)
        # Non-string content (e.g. multimodal blocks) bypasses budget.
        original = ToolMessage(content=[{"type": "text", "text": "x"}], tool_call_id="c", name="t")

        async def handler(req: ToolCallRequest) -> ToolMessage:
            return original

        result = await mw.awrap_tool_call(_request(), handler)
        assert result is original


class TestSyncWrapToolCall:
    def test_small_tool_message_passes_through(self, tmp_path: Path) -> None:
        mw = ToolOutputBudgetMiddleware(output_dir=str(tmp_path), max_chars=10_000)
        original = ToolMessage(content="small", tool_call_id="call-1", name="t")

        def handler(req: ToolCallRequest) -> ToolMessage:
            return original

        result = mw.wrap_tool_call(_request(), handler)
        assert result is original

    def test_oversize_tool_message_externalised_to_disk(self, tmp_path: Path) -> None:
        mw = ToolOutputBudgetMiddleware(output_dir=str(tmp_path), max_chars=200)
        big_content = "Z" * 2000
        original = ToolMessage(content=big_content, tool_call_id="call-1", name="search_jq_dict")

        def handler(req: ToolCallRequest) -> ToolMessage:
            return original

        result = mw.wrap_tool_call(_request("search_jq_dict", "call-1"), handler)
        assert isinstance(result, ToolMessage)
        files = list(tmp_path.glob("search_jq_dict-*.txt"))
        assert len(files) == 1
        assert isinstance(result.content, str)
        assert str(files[0]) in result.content
