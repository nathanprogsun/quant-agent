"""LangChain tools for jq_kb (phase-gated by PR)."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from langchain_core.tools import tool

from app.core.jq_kb.retrievers import (
    create_default_jq_api_retriever,
    create_default_jq_dict_retriever,
    create_default_jq_strategy_retriever,
)


def _format_api_hits(hits: list[Any]) -> str:
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


def _format_dict_hits(hits: list[Any]) -> str:
    if not hits:
        return "未找到相关聚宽数据字典条目。请换关键词或提供 code。"
    parts: list[str] = []
    for i, hit in enumerate(hits, 1):
        meta = hit.metadata
        code = meta.get("code", hit.chunk_id)
        name = meta.get("name", "")
        dict_type = meta.get("dict_type", "")
        header = f"## {i}. {code} {name} ({dict_type}, score={hit.score:.3f})"
        body = hit.document[:2500]
        parts.append(f"{header}\n\n{body}")
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
    - 行业/概念/指数(HY001) — 使用 search_jq_dict
    - 策略范例 — 使用 search_jq_strategy

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
    return _format_api_hits(hits)


@tool
async def search_jq_dict(
    query: str,
    code: str = "",
) -> str:
    """在聚宽数据字典中检索行业、概念、指数、行情字段、代码后缀等实体含义。

    适用场景:
    - 行业代码:"HY001 是什么行业"、"农林牧渔对应代码"
    - 概念板块:"人工智能概念代码"、"GN001"
    - 指数:"沪深300代码"、"000300"
    - 行情字段:"close 字段含义"、"pe_ratio 单位"
    - 代码后缀:".XSHG 是什么"、"上交所后缀"

    不适用:
    - API 函数用法 — 使用 search_jq_api
    - 策略范例 — 使用 search_jq_strategy

    Args:
        query: 自然语言检索问题
        code: 可选,精确代码(如 HY001、close、.XSHG)
    """
    retriever = _get_jq_dict_retriever()
    hits = await retriever.retrieve(
        query,
        code=code.strip(),
        top_k=5,
    )
    return _format_dict_hits(hits)


def _format_strategy_hits(hits: list[Any]) -> str:
    if not hits:
        return "未找到相关聚宽精选策略。请换关键词或指定年份/策略类型。"
    parts: list[str] = []
    for i, hit in enumerate(hits, 1):
        meta = hit.metadata
        title = meta.get("title", hit.chunk_id)
        layer = meta.get("layer", "")
        year = meta.get("year", "")
        stype = meta.get("strategy_type", "")
        header = f"## {i}. {title} ({layer}, {year}, {stype}, score={hit.score:.3f})"
        body = hit.document[:3500]
        parts.append(f"{header}\n\n{body}")
    return "\n\n---\n\n".join(parts)


@tool
async def search_jq_strategy(
    query: str,
    year: int = 0,
    strategy_type: str = "",
) -> str:
    """在 2020-2024 聚宽精选策略库中检索实战策略思路、代码片段与 API 用法。

    适用场景:
    - 策略实现:"ETF 轮动怎么写"、"小市值选股策略"
    - 因子组合:"F-Score 选股"、"多因子策略"
    - 完整代码:"initialize 函数示例"
    - 反向查询:"用到 get_fundamentals 的策略"

    不适用:
    - API 函数签名 — 使用 search_jq_api
    - 行业/字段代码 — 使用 search_jq_dict

    Args:
        query: 自然语言检索问题
        year: 可选,按年份过滤(如 2023)
        strategy_type: 可选,策略类型过滤(如 "ETF 轮动")
    """
    retriever = _get_jq_strategy_retriever()
    hits = await retriever.retrieve(
        query,
        year=year,
        strategy_type=strategy_type.strip(),
        top_k=5,
    )
    return _format_strategy_hits(hits)


@lru_cache(maxsize=1)
def _get_jq_strategy_retriever() -> Any:
    return create_default_jq_strategy_retriever()


@lru_cache(maxsize=1)
def _get_jq_api_retriever() -> Any:
    return create_default_jq_api_retriever()


@lru_cache(maxsize=1)
def _get_jq_dict_retriever() -> Any:
    return create_default_jq_dict_retriever()


def get_tools(*, pr_phase: int = 1) -> list[Any]:
    """Return jq_kb tools enabled for the given PR phase."""
    tools: list[Any] = []
    if pr_phase >= 1:
        tools.append(search_jq_api)
    if pr_phase >= 2:
        tools.append(search_jq_dict)
    if pr_phase >= 3:
        tools.append(search_jq_strategy)
    return tools
