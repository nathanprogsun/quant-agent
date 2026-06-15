"""Analyze SSE streaming API."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI

from app.core.backtest.types import BacktestMetrics
from app.core.dc42.analyzer import DC42Analyzer
from app.core.dc42.retriever import create_default_retriever
from app.db.models.user import User
from app.settings import get_settings
from app.web.api.analyze.schemas import AnalyzeStreamRequest
from app.web.api.deps import get_current_user

router = APIRouter(prefix="/api/v1/analyze", tags=["analyze"])


def format_analyze_sse(payload: dict[str, Any]) -> str:
    data = json.dumps(payload, ensure_ascii=False, default=str)
    return f"data: {data}\n\n"


def _build_analyzer() -> DC42Analyzer:
    settings = get_settings()

    async def llm_call(prompt: str) -> Any:
        model = ChatOpenAI(
            model=settings.model,
            api_key=settings.openai_api_key.get_secret_value(),
            base_url=settings.openai_base_url,
            streaming=False,
        )
        return await model.ainvoke([HumanMessage(content=prompt)])

    retriever = create_default_retriever()
    return DC42Analyzer(llm_call=llm_call, retriever=retriever)


async def analyze_event_stream(body: AnalyzeStreamRequest) -> AsyncIterator[str]:
    analyzer = _build_analyzer()
    metrics = BacktestMetrics(
        annual_return=body.metrics.annual_return,
        sharpe=body.metrics.sharpe,
        max_drawdown=body.metrics.max_drawdown,
        volatility=body.metrics.volatility,
        win_rate=body.metrics.win_rate,
        raw=body.metrics.raw,
    )
    code_summary = body.code.strip() or "用户策略代码"

    async for chunk in analyzer.analyze(
        metrics=metrics,
        code_summary=code_summary,
        thread_id=body.thread_id,
    ):
        yield format_analyze_sse({"type": "analyze_delta", "content": chunk})

    yield format_analyze_sse({"type": "analyze_done"})


@router.post("/stream")
async def analyze_stream(
    body: AnalyzeStreamRequest,
    current_user: Annotated[User, Depends(get_current_user)],
) -> StreamingResponse:
    """Stream DC42 comparative analysis via SSE."""
    _ = current_user
    return StreamingResponse(
        analyze_event_stream(body),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
