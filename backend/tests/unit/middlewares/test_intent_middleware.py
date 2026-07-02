"""Tests for IntentMiddleware."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from app.core.chat.middlewares.intent_middleware import (
    IntentMiddleware,
    _extract_intent,
)


@pytest.fixture
def middleware() -> IntentMiddleware:
    return IntentMiddleware()


@pytest.fixture
def runtime() -> MagicMock:
    return MagicMock()


class TestExtractIntent:
    def test_xml_tag(self) -> None:
        content = "<intent>strategy_build</intent>\n这是策略代码..."
        assert _extract_intent(content) == "strategy_build"

    def test_inline_marker(self) -> None:
        content = "意图: backtest\n我来帮你执行回测。"
        assert _extract_intent(content) == "backtest"

    def test_chinese_colon(self) -> None:
        content = "意图：market_query\n查询结果如下..."
        assert _extract_intent(content) == "market_query"

    def test_case_insensitive(self) -> None:
        content = "Intent: Chat\n你好！"
        assert _extract_intent(content) == "chat"

    def test_returns_none_when_no_intent(self) -> None:
        assert _extract_intent("普通回复内容") is None

    def test_all_valid_intents(self) -> None:
        for intent in [
            "chat",
            "strategy_build",
            "backtest",
            "market_query",
            "code_review",
            "file_analysis",
            "unknown",
        ]:
            assert _extract_intent(f"意图: {intent}") == intent

    def test_invalid_intent_ignored(self) -> None:
        assert _extract_intent("意图: invalid_intent") is None


class TestIntentMiddleware:
    @pytest.mark.asyncio
    async def test_extracts_intent_from_ai_message(
        self, middleware: IntentMiddleware, runtime: MagicMock
    ) -> None:
        state: dict[str, Any] = {
            "messages": [
                HumanMessage(content="帮我回测一下"),
                AIMessage(content="意图: backtest\n我来执行回测。"),
            ],
        }
        result = await middleware.aafter_model(state, runtime)
        assert result is not None
        assert result["intent"] == "backtest"

    @pytest.mark.asyncio
    async def test_returns_none_when_no_intent(
        self, middleware: IntentMiddleware, runtime: MagicMock
    ) -> None:
        state: dict[str, Any] = {
            "messages": [
                HumanMessage(content="你好"),
                AIMessage(content="你好！有什么可以帮你的？"),
            ],
        }
        assert await middleware.aafter_model(state, runtime) is None

    @pytest.mark.asyncio
    async def test_skips_when_intent_already_set(
        self, middleware: IntentMiddleware, runtime: MagicMock
    ) -> None:
        state: dict[str, Any] = {
            "intent": "chat",
            "messages": [
                HumanMessage(content="你好"),
                AIMessage(content="意图: chat\n你好！"),
            ],
        }
        assert await middleware.aafter_model(state, runtime) is None

    @pytest.mark.asyncio
    async def test_skips_tool_call_messages(
        self, middleware: IntentMiddleware, runtime: MagicMock
    ) -> None:
        state: dict[str, Any] = {
            "messages": [
                HumanMessage(content="查 API"),
                AIMessage(
                    content="",
                    tool_calls=[{"id": "tc_1", "name": "search_jq_api", "args": {}}],
                ),
            ],
        }
        assert await middleware.aafter_model(state, runtime) is None

    @pytest.mark.asyncio
    async def test_empty_messages(self, middleware: IntentMiddleware, runtime: MagicMock) -> None:
        state: dict[str, Any] = {"messages": []}
        assert await middleware.aafter_model(state, runtime) is None
