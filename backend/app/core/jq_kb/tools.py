"""LangChain tools for jq_kb (phase-gated by PR)."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from langchain_core.tools import tool

from app.core.jq_kb.retrievers import create_default_jq_api_retriever


def _format_hits(hits: list[Any]) -> str:
    if not hits:
        return "未找到相关聚宽 API 文档。请换关键词或提供 function_name。"
    parts: list[str] = []
    for i, hit in enumerate(hits, 1):
        meta = hit.metadata
        header = f"## {i}. {meta.get('function_name', hit.chunk_id)} (score={hit.score:.3f})"
        url = meta.get("source_url", "")
        body = hit.document[:2500]
        parts.append(f"{header}\n来源: {url}\n\n{body}")
    return "\n\n---\n\n".join(parts)


@tool
async def search_jq_api(
    query: str,
    function_name: str = "",
) -> str:
    """在聚宽 API 文档库中检索函数签名、参数、返回值、示例代码和环境约束(♠ 标识)。

    适用场景:
    - 函数用法:"get_price 怎么用"、"order_target 的参数"
    - 函数报错:"为什么报参数错误"
    - 函数支持范围:"支持哪些频率"
    - 涉及 get_*/set_*/order_*/create_*/run_*/history 等函数名

    不适用:
    - 行业/概念/指数(HY001) — PR2 search_jq_dict
    - 策略范例 — PR3 search_jq_strategy

    Args:
        query: 自然语言检索问题
        function_name: 可选,精确函数名过滤(如 get_price)
    """
    retriever = _get_jq_api_retriever()
    hits = await retriever.retrieve(
        query,
        function_name=function_name.strip(),
        top_k=5,
    )
    return _format_hits(hits)


@lru_cache(maxsize=1)
def _get_jq_api_retriever() -> Any:
    return create_default_jq_api_retriever()


def get_tools(*, pr_phase: int = 1) -> list[Any]:
    """Return jq_kb tools enabled for the given PR phase."""
    tools: list[Any] = []
    if pr_phase >= 1:
        tools.append(search_jq_api)
    return tools
