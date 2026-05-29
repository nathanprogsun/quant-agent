"""DC42Analyzer tests — mock LLM calls."""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.core.backtest.types import BacktestMetrics
from app.core.dc42.analyzer import DC42Analyzer


def _make_llm_call(response_text: str) -> AsyncMock:
    """Create a mock LLM callable that returns a response with .content."""
    response = AsyncMock()
    response.content = response_text
    return AsyncMock(return_value=response)


@pytest.mark.asyncio
async def test_analyze_yields_streaming_chunks():
    """analyze should yield markdown chunks via async iterator."""
    mock_llm = _make_llm_call(
        "## 对标 DC42\n\n### 小市值策略对比\n你的策略年化 15%，DC42 平均 12%。\n\n### 改进建议\n1. 加入止损"
    )

    analyzer = DC42Analyzer(llm_call=mock_llm, retriever=AsyncMock())
    metrics = BacktestMetrics(annual_return=0.15, sharpe=1.2, max_drawdown=0.1)

    chunks = []
    async for chunk in analyzer.analyze(
        metrics=metrics,
        code_summary="小市值策略",
        thread_id=uuid4(),
    ):
        chunks.append(chunk)

    assert len(chunks) > 0
    assert any("DC42" in c for c in chunks)


@pytest.mark.asyncio
async def test_analyze_includes_metrics():
    """analyze prompt should include backtest metrics."""
    mock_llm = _make_llm_call("分析结果")

    mock_retriever = AsyncMock()
    mock_retriever.retrieve_by_intent = AsyncMock(return_value=AsyncMock(
        chunks=[], strategy_names=["策略A"], summary="test"
    ))

    analyzer = DC42Analyzer(llm_call=mock_llm, retriever=mock_retriever)
    metrics = BacktestMetrics(annual_return=0.20, sharpe=1.5, max_drawdown=0.08)

    chunks = []
    async for chunk in analyzer.analyze(metrics=metrics, code_summary="test", thread_id=uuid4()):
        chunks.append(chunk)

    # Verify LLM was called with metrics in prompt
    call_args = mock_llm.call_args
    prompt = str(call_args)
    assert "0.2" in prompt or "20" in prompt  # annual_return
