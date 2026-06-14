"""Unit tests for title middleware."""

from langchain_core.messages import AIMessage, HumanMessage

from app.core.chat.middlewares.title_middleware import TitleMiddleware


async def test_title_middleware_writes_title_field() -> None:
    middleware = TitleMiddleware()
    state = {"messages": [HumanMessage(content="稳健型ETF策略")]}

    result = await middleware.after_model(state, {})

    assert result == {"title": "稳健型ETF策略"}


async def test_title_middleware_skips_when_title_exists() -> None:
    middleware = TitleMiddleware()
    state = {
        "title": "已有标题",
        "messages": [HumanMessage(content="新消息")],
    }

    result = await middleware.after_model(state, {})

    assert result is None


async def test_title_middleware_truncates_long_titles() -> None:
    middleware = TitleMiddleware()
    long_content = "a" * 60
    state = {"messages": [HumanMessage(content=long_content)]}

    result = await middleware.after_model(state, {})

    assert result is not None
    assert result["title"].endswith("...")
    assert len(result["title"]) == 53


async def test_title_middleware_ignores_non_human_messages() -> None:
    middleware = TitleMiddleware()
    state = {"messages": [AIMessage(content="assistant only")]}

    result = await middleware.after_model(state, {})

    assert result is None
