"""Integration tests for DC42 context injection into chat prompts."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from langchain_core.messages import HumanMessage, SystemMessage

from app.core.chat.middlewares.dc42_context_middleware import DC42ContextMiddleware
from app.core.dc42.types import RetrievalResult, StrategyChunk
from app.core.generation.context_builder import format_dc42_context


def test_format_dc42_context_renders_chunk_content() -> None:
    result = RetrievalResult(
        chunks=[
            StrategyChunk(
                chunk_id="c1",
                strategy_id="s1",
                chunk_type="intent",
                content="小市值因子选股模板",
                metadata={"strategy_id": "s1"},
            ),
        ],
        strategy_names=["small_cap_template"],
        summary="找到 1 个相关片段",
    )

    formatted = format_dc42_context(result)

    assert "小市值因子选股模板" in formatted
    assert "small_cap" in formatted or "s1" in formatted


@pytest.mark.asyncio
async def test_dc42_context_middleware_injects_retrieved_chunks() -> None:
    retriever = AsyncMock()
    retriever.retrieve_by_intent.return_value = RetrievalResult(
        chunks=[
            StrategyChunk(
                chunk_id="c1",
                strategy_id="s1",
                chunk_type="intent",
                content="DC42_PROMPT_MARKER: 使用 jq.get_fundamentals 筛选小市值",
                metadata={"strategy_id": "s1"},
            ),
        ],
        strategy_names=["small_cap"],
        summary="找到 1 个相关 DC42 策略片段",
    )

    middleware = DC42ContextMiddleware(retriever=retriever)
    state = {
        "messages": [
            SystemMessage(content="你是一个量化投资分析助手"),
            HumanMessage(content="帮我写一个小市值策略"),
        ],
    }

    updated = await middleware.before_model(state, {})

    assert updated is not None
    system_content = updated["messages"][0].content
    assert "DC42_PROMPT_MARKER" in system_content
    retriever.retrieve_by_intent.assert_awaited_once_with("帮我写一个小市值策略")


@pytest.mark.asyncio
async def test_dc42_context_middleware_degrades_when_retrieval_fails() -> None:
    retriever = AsyncMock()
    retriever.retrieve_by_intent.side_effect = RuntimeError("chroma unavailable")

    middleware = DC42ContextMiddleware(retriever=retriever)
    state = {
        "messages": [
            SystemMessage(content="base"),
            HumanMessage(content="策略参数怎么设"),
        ],
    }

    updated = await middleware.before_model(state, {})

    assert updated is None
    retriever.retrieve_by_intent.assert_awaited_once()
