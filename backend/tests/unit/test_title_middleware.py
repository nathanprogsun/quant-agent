"""Unit tests for title middleware."""

from unittest.mock import AsyncMock, patch

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.runtime import Runtime

from app.core.chat.middlewares.title_middleware import TitleMiddleware


async def test_title_middleware_generates_after_first_exchange() -> None:
    middleware = TitleMiddleware()
    state = {
        "messages": [
            HumanMessage(content="稳健型ETF策略"),
            AIMessage(content="可以从低波动宽基 ETF 入手。"),
        ]
    }

    with patch.object(
        TitleMiddleware,
        "_generate_title",
        new=AsyncMock(return_value="稳健型 ETF 策略咨询"),
    ):
        result = await middleware.after_model(state, Runtime())

    assert result == {"title": "稳健型 ETF 策略咨询"}


async def test_title_middleware_skips_when_title_exists() -> None:
    middleware = TitleMiddleware()
    state = {
        "title": "已有标题",
        "messages": [
            HumanMessage(content="新消息"),
            AIMessage(content="回复"),
        ],
    }

    result = await middleware.after_model(state, Runtime())

    assert result is None


async def test_title_middleware_waits_for_assistant_reply() -> None:
    middleware = TitleMiddleware()
    state = {"messages": [HumanMessage(content="稳健型ETF策略")]}

    result = await middleware.after_model(state, Runtime())

    assert result is None


async def test_title_middleware_uses_greeting_fallback() -> None:
    middleware = TitleMiddleware()

    with (
        patch.object(
            TitleMiddleware,
            "_generate_title",
            wraps=middleware._generate_title,
        ) as generate_title,
        patch("app.core.chat.middlewares.title_middleware.ChatOpenAI") as mock_chat_openai,
    ):
        mock_chat_openai.return_value.ainvoke = AsyncMock(side_effect=RuntimeError("offline"))
        title = await generate_title("hi", "你好，有什么可以帮你？")

    assert title == "新对话"


async def test_title_middleware_generates_after_tool_loop() -> None:
    middleware = TitleMiddleware()
    state = {
        "messages": [
            HumanMessage(content="帮我检查参数"),
            AIMessage(content="", tool_calls=[{"name": "validate", "args": {}, "id": "1"}]),
            AIMessage(content="参数校验通过，可以继续回测。"),
        ]
    }

    with patch.object(
        TitleMiddleware,
        "_generate_title",
        new=AsyncMock(return_value="参数校验"),
    ):
        result = await middleware.after_model(state, Runtime())

    assert result == {"title": "参数校验"}


async def test_title_middleware_ignores_tool_call_only_reply() -> None:
    middleware = TitleMiddleware()
    state = {
        "messages": [
            HumanMessage(content="帮我检查参数"),
            AIMessage(content="", tool_calls=[{"name": "validate", "args": {}, "id": "1"}]),
        ]
    }

    result = await middleware.after_model(state, Runtime())

    assert result is None
