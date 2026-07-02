"""Tests for CodePersistenceMiddleware."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from app.core.chat.middlewares.code_persistence_middleware import (
    CodePersistenceMiddleware,
    _extract_python_code,
)


@pytest.fixture
def middleware() -> CodePersistenceMiddleware:
    return CodePersistenceMiddleware()


@pytest.fixture
def runtime() -> MagicMock:
    return MagicMock()


class TestExtractPythonCode:
    def test_extracts_single_block(self) -> None:
        content = "Here is the strategy:\n```python\nprint('hello')\n```\nDone."
        assert _extract_python_code(content) == "print('hello')"

    def test_extracts_longest_block(self) -> None:
        content = (
            "Short:\n```python\nx = 1\n```\n"
            "Long:\n```python\nfor i in range(100):\n    print(i)\n```\n"
        )
        result = _extract_python_code(content)
        assert result is not None
        assert "for i in range(100):" in result

    def test_returns_none_when_no_code(self) -> None:
        assert _extract_python_code("Just plain text, no code.") is None

    def test_returns_none_for_empty_code_block(self) -> None:
        assert _extract_python_code("```python\n\n```") is None

    def test_case_insensitive(self) -> None:
        content = "```Python\nprint(1)\n```"
        assert _extract_python_code(content) == "print(1)"


class TestCodePersistenceMiddleware:
    @pytest.mark.asyncio
    async def test_extracts_code_from_final_ai_message(
        self, middleware: CodePersistenceMiddleware, runtime: MagicMock
    ) -> None:
        state: dict[str, Any] = {
            "messages": [
                HumanMessage(content="写一个策略"),
                AIMessage(content="好的：\n```python\ndef strategy():\n    pass\n```"),
            ],
        }
        result = await middleware.aafter_model(state, runtime)
        assert result is not None
        assert "code" in result
        assert "def strategy():" in result["code"]

    @pytest.mark.asyncio
    async def test_returns_none_when_no_code(
        self, middleware: CodePersistenceMiddleware, runtime: MagicMock
    ) -> None:
        state: dict[str, Any] = {
            "messages": [
                HumanMessage(content="你好"),
                AIMessage(content="你好！有什么可以帮你的？"),
            ],
        }
        assert await middleware.aafter_model(state, runtime) is None

    @pytest.mark.asyncio
    async def test_returns_none_for_tool_call_message(
        self, middleware: CodePersistenceMiddleware, runtime: MagicMock
    ) -> None:
        state: dict[str, Any] = {
            "messages": [
                HumanMessage(content="写策略"),
                AIMessage(
                    content="",
                    tool_calls=[{"id": "tc_1", "name": "lint_code_tool", "args": {"code": "x"}}],
                ),
            ],
        }
        assert await middleware.aafter_model(state, runtime) is None

    @pytest.mark.asyncio
    async def test_skips_when_code_unchanged(
        self, middleware: CodePersistenceMiddleware, runtime: MagicMock
    ) -> None:
        state: dict[str, Any] = {
            "code": "def strategy():\n    pass",
            "messages": [
                HumanMessage(content="确认"),
                AIMessage(content="```python\ndef strategy():\n    pass\n```"),
            ],
        }
        assert await middleware.aafter_model(state, runtime) is None

    @pytest.mark.asyncio
    async def test_updates_when_code_changes(
        self, middleware: CodePersistenceMiddleware, runtime: MagicMock
    ) -> None:
        state: dict[str, Any] = {
            "code": "old code",
            "messages": [
                HumanMessage(content="修改策略"),
                AIMessage(content="```python\ndef new_strategy():\n    pass\n```"),
            ],
        }
        result = await middleware.aafter_model(state, runtime)
        assert result is not None
        assert "def new_strategy():" in result["code"]

    @pytest.mark.asyncio
    async def test_empty_messages(
        self, middleware: CodePersistenceMiddleware, runtime: MagicMock
    ) -> None:
        state: dict[str, Any] = {"messages": []}
        assert await middleware.aafter_model(state, runtime) is None
