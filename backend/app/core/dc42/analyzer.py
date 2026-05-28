"""DC42 comparative analyzer — streams analysis via LLM."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Awaitable, Callable
from uuid import UUID

from app.core.backtest.types import BacktestMetrics
from app.core.dc42.retriever import DC42Retriever


LLMCall = Callable[[str], Awaitable[Any]]


class DC42Analyzer:
    """Analyze backtest results against DC42 knowledge base."""

    def __init__(self, llm_call: LLMCall, retriever: DC42Retriever) -> None:
        self._llm_call = llm_call
        self._retriever = retriever

    async def analyze(
        self,
        metrics: BacktestMetrics,
        code_summary: str,
        thread_id: UUID,
    ) -> AsyncIterator[str]:
        """Stream analysis comparing backtest results to DC42 strategies."""
        # Retrieve relevant DC42 context
        dc42_result = await self._retriever.retrieve_by_intent(code_summary)

        metrics_text = self._format_metrics(metrics)
        dc42_text = dc42_result.summary
        strategy_names = ", ".join(dc42_result.strategy_names[:5]) if dc42_result.strategy_names else "无"

        prompt = f"""你是量化策略分析专家。请对比以下回测结果和 DC42 知识库，给出分析。

## 回测指标
{metrics_text}

## 策略描述
{code_summary}

## DC42 参考策略
{dc42_text}
涉及策略: {strategy_names}

请输出:
1. 对标 DC42 的对比分析
2. 策略优劣势
3. 改进建议 (A/B/C 三个方案)
"""

        response = await self._llm_call(prompt)
        content = response.content if hasattr(response, "content") else str(response)

        # Stream in chunks
        chunk_size = 100
        for i in range(0, len(content), chunk_size):
            yield content[i : i + chunk_size]

    def _format_metrics(self, metrics: BacktestMetrics) -> str:
        lines = []
        if metrics.annual_return is not None:
            lines.append(f"- 年化收益: {metrics.annual_return:.2%}")
        if metrics.sharpe is not None:
            lines.append(f"- 夏普比率: {metrics.sharpe:.2f}")
        if metrics.max_drawdown is not None:
            lines.append(f"- 最大回撤: {metrics.max_drawdown:.2%}")
        if metrics.volatility is not None:
            lines.append(f"- 波动率: {metrics.volatility:.2%}")
        if metrics.win_rate is not None:
            lines.append(f"- 胜率: {metrics.win_rate:.2%}")
        return "\n".join(lines) if lines else "无指标数据"
