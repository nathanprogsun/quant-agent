"""Tests for ToolErrorHandlingMiddleware.

Verifies that tool exceptions raised in the handler are converted into
``ToolMessage(status="error")`` results so the run can continue, and that
LangGraph control-flow signals (``GraphBubbleUp``) propagate unchanged.
"""

from __future__ import annotations

from typing import Any

import pytest
from langchain_core.messages import ToolMessage
from langgraph.errors import GraphBubbleUp
from langgraph.prebuilt.tool_node import ToolCallRequest

from app.core.chat.middlewares.tool_error_handling_middleware import ToolErrorHandlingMiddleware


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


class TestSyncWrapToolCall:
    def test_success_passes_through_handler_result(self) -> None:
        mw = ToolErrorHandlingMiddleware()
        expected = ToolMessage(content="ok", tool_call_id="call-1", name="t")

        def handler(req: ToolCallRequest) -> ToolMessage:
            return expected

        result = mw.wrap_tool_call(_request(), handler)
        assert result is expected

    def test_exception_becomes_error_tool_message(self) -> None:
        mw = ToolErrorHandlingMiddleware()

        def handler(req: ToolCallRequest) -> ToolMessage:
            raise RuntimeError("embedding provider 503")

        result = mw.wrap_tool_call(_request("search_jq_api", "call-9"), handler)
        assert isinstance(result, ToolMessage)
        assert result.status == "error"
        assert result.tool_call_id == "call-9"
        assert result.name == "search_jq_api"
        assert "search_jq_api" in result.content
        assert "RuntimeError" in result.content
        assert "embedding provider 503" in result.content

    def test_long_exception_detail_is_truncated(self) -> None:
        mw = ToolErrorHandlingMiddleware()
        long_detail = "x" * 2000

        def handler(req: ToolCallRequest) -> ToolMessage:
            raise ValueError(long_detail)

        result = mw.wrap_tool_call(_request(), handler)
        assert isinstance(result, ToolMessage)
        # detail capped at 500 chars then "...": total content may be longer
        # but the detail substring is bounded.
        assert long_detail not in result.content
        assert "..." in result.content

    def test_graph_bubble_up_propagates(self) -> None:
        mw = ToolErrorHandlingMiddleware()

        def handler(req: ToolCallRequest) -> ToolMessage:
            raise GraphBubbleUp()

        with pytest.raises(GraphBubbleUp):
            mw.wrap_tool_call(_request(), handler)


class TestAsyncWrapToolCall:
    async def test_success_passes_through_handler_result(self) -> None:
        mw = ToolErrorHandlingMiddleware()
        expected = ToolMessage(content="ok", tool_call_id="call-1", name="t")

        async def handler(req: ToolCallRequest) -> ToolMessage:
            return expected

        result = await mw.awrap_tool_call(_request(), handler)
        assert result is expected

    async def test_exception_becomes_error_tool_message(self) -> None:
        mw = ToolErrorHandlingMiddleware()

        async def handler(req: ToolCallRequest) -> ToolMessage:
            raise TimeoutError("provider timeout")

        result = await mw.awrap_tool_call(_request("search_jq_dict", "call-2"), handler)
        assert isinstance(result, ToolMessage)
        assert result.status == "error"
        assert result.tool_call_id == "call-2"
        assert result.name == "search_jq_dict"
        assert "TimeoutError" in result.content
        assert "provider timeout" in result.content

    async def test_graph_bubble_up_propagates(self) -> None:
        mw = ToolErrorHandlingMiddleware()

        async def handler(req: ToolCallRequest) -> ToolMessage:
            raise GraphBubbleUp()

        with pytest.raises(GraphBubbleUp):
            await mw.awrap_tool_call(_request(), handler)

    async def test_missing_tool_call_id_uses_sentinel(self) -> None:
        """A tool call without an id still produces an error ToolMessage
        with a sentinel ``tool_call_id`` so the ToolNode can pair it back.
        """
        mw = ToolErrorHandlingMiddleware()

        async def handler(req: ToolCallRequest) -> Any:
            raise RuntimeError("boom")

        req = ToolCallRequest(
            tool_call={"name": "t", "args": {}, "id": "", "type": "tool_call"},
            tool=None,  # type: ignore[arg-type]
            state={"messages": []},
            runtime=None,  # type: ignore[arg-type]
        )
        result = await mw.awrap_tool_call(req, handler)
        assert isinstance(result, ToolMessage)
        assert result.status == "error"
        # Sentinel id from the middleware (non-empty so ToolNode can accept).
        assert result.tool_call_id
