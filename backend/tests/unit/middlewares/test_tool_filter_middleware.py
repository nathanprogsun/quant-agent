"""Tests for ToolFilterMiddleware — intent-based tool schema filtering."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.core.chat.middlewares.tool_filter_middleware import (
    INTENT_TOOL_MAP,
    ToolFilterMiddleware,
)


@dataclass
class FakeTool:
    name: str


@dataclass
class FakeRequest:
    tools: list[Any] = field(default_factory=list)
    state: dict[str, Any] = field(default_factory=dict)

    def override(self, *, tools: list[Any]) -> FakeRequest:
        return FakeRequest(tools=tools, state=self.state)


def _make_tools(*names: str) -> list[FakeTool]:
    return [FakeTool(name=n) for n in names]


ALL_TOOL_NAMES = [
    "lint_code_tool",
    "validate_strategy_parameters",
    "read_file",
    "ask_clarification",
    "search_jq_api",
    "search_jq_dict",
    "search_jq_strategy",
    "tool_search",
    "mcp_tool_alpha",
]


@pytest.mark.asyncio
async def test_no_intent_sends_all_tools() -> None:
    """When intent is None (first turn), all tools are sent."""
    mw = ToolFilterMiddleware()
    tools = _make_tools(*ALL_TOOL_NAMES)
    request = FakeRequest(tools=tools, state={"intent": None})
    handler = AsyncMock(return_value="ok")

    await mw.awrap_model_call(request, handler)
    sent = handler.call_args[0][0]
    assert len(sent.tools) == len(ALL_TOOL_NAMES)


@pytest.mark.asyncio
async def test_unknown_intent_sends_all_tools() -> None:
    """Unknown intent is not in INTENT_TOOL_MAP — all tools sent."""
    mw = ToolFilterMiddleware()
    tools = _make_tools(*ALL_TOOL_NAMES)
    request = FakeRequest(tools=tools, state={"intent": "unknown"})
    handler = AsyncMock(return_value="ok")

    await mw.awrap_model_call(request, handler)
    sent = handler.call_args[0][0]
    assert len(sent.tools) == len(ALL_TOOL_NAMES)


@pytest.mark.asyncio
async def test_chat_intent_filters_to_relevant_tools() -> None:
    """Chat intent only sends ask_clarification + read_file."""
    mw = ToolFilterMiddleware()
    tools = _make_tools(*ALL_TOOL_NAMES)
    request = FakeRequest(tools=tools, state={"intent": "chat"})
    handler = AsyncMock(return_value="ok")

    await mw.awrap_model_call(request, handler)
    sent = handler.call_args[0][0]
    sent_names = {t.name for t in sent.tools}
    assert sent_names == {"ask_clarification", "read_file"}


@pytest.mark.asyncio
async def test_strategy_build_includes_all_relevant() -> None:
    """strategy_build intent includes lint, validate, jq_kb, tool_search."""
    mw = ToolFilterMiddleware()
    tools = _make_tools(*ALL_TOOL_NAMES)
    request = FakeRequest(tools=tools, state={"intent": "strategy_build"})
    handler = AsyncMock(return_value="ok")

    await mw.awrap_model_call(request, handler)
    sent = handler.call_args[0][0]
    sent_names = {t.name for t in sent.tools}
    expected = INTENT_TOOL_MAP["strategy_build"]
    assert sent_names == expected


@pytest.mark.asyncio
async def test_market_query_excludes_code_tools() -> None:
    """market_query intent excludes lint_code_tool, validate, read_file."""
    mw = ToolFilterMiddleware()
    tools = _make_tools(*ALL_TOOL_NAMES)
    request = FakeRequest(tools=tools, state={"intent": "market_query"})
    handler = AsyncMock(return_value="ok")

    await mw.awrap_model_call(request, handler)
    sent = handler.call_args[0][0]
    sent_names = {t.name for t in sent.tools}
    assert "lint_code_tool" not in sent_names
    assert "validate_strategy_parameters" not in sent_names
    assert "read_file" not in sent_names
    assert "ask_clarification" not in sent_names


@pytest.mark.asyncio
async def test_code_review_includes_lint_and_validate() -> None:
    """code_review intent includes lint + validate + read_file."""
    mw = ToolFilterMiddleware()
    tools = _make_tools(*ALL_TOOL_NAMES)
    request = FakeRequest(tools=tools, state={"intent": "code_review"})
    handler = AsyncMock(return_value="ok")

    await mw.awrap_model_call(request, handler)
    sent = handler.call_args[0][0]
    sent_names = {t.name for t in sent.tools}
    assert "lint_code_tool" in sent_names
    assert "validate_strategy_parameters" in sent_names
    assert "read_file" in sent_names
    assert "ask_clarification" not in sent_names


@pytest.mark.asyncio
async def test_file_analysis_excludes_code_tools() -> None:
    """file_analysis intent excludes lint, validate, ask_clarification."""
    mw = ToolFilterMiddleware()
    tools = _make_tools(*ALL_TOOL_NAMES)
    request = FakeRequest(tools=tools, state={"intent": "file_analysis"})
    handler = AsyncMock(return_value="ok")

    await mw.awrap_model_call(request, handler)
    sent = handler.call_args[0][0]
    sent_names = {t.name for t in sent.tools}
    assert "lint_code_tool" not in sent_names
    assert "validate_strategy_parameters" not in sent_names
    assert "ask_clarification" not in sent_names
    assert "read_file" in sent_names


@pytest.mark.asyncio
async def test_empty_state_sends_all_tools() -> None:
    """Empty state (no intent key) sends all tools."""
    mw = ToolFilterMiddleware()
    tools = _make_tools(*ALL_TOOL_NAMES)
    request = FakeRequest(tools=tools, state={})
    handler = AsyncMock(return_value="ok")

    await mw.awrap_model_call(request, handler)
    sent = handler.call_args[0][0]
    assert len(sent.tools) == len(ALL_TOOL_NAMES)


def test_sync_wrap_model_call() -> None:
    """Sync wrap_model_call also filters tools."""
    mw = ToolFilterMiddleware()
    tools = _make_tools(*ALL_TOOL_NAMES)
    request = FakeRequest(tools=tools, state={"intent": "chat"})

    def handler(req: FakeRequest) -> FakeRequest:
        return req

    result = mw.wrap_model_call(request, handler)
    assert len(result.tools) == 2  # ask_clarification + read_file
