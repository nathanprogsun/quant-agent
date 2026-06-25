"""Chunk jq_strategy posts into summary / entity / code layers."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.core.jq_kb.utils import json_safe_value

from app.core.jq_kb.ast_parser import extract_entities, extract_function_code
from app.core.jq_kb.schemas import JqStrategyChunk, Source, StrategyLayer, StrategySummary

logger = logging.getLogger(__name__)

_STRATEGY_TYPE_HINTS: list[tuple[str, str]] = [
    ("etf", "ETF 轮动"),
    ("ETF", "ETF 轮动"),
    ("小市值", "小市值"),
    ("F-Score", "F-Score 选股"),
    ("Fscore", "F-Score 选股"),
    ("动量", "动量轮动"),
    ("网格", "ETF 网格"),
    ("多因子", "多因子"),
    ("机器学习", "机器学习"),
    ("配对", "配对交易"),
]


def _infer_strategy_type(title: str) -> str:
    for needle, label in _STRATEGY_TYPE_HINTS:
        if needle in title:
            return label
    return "其他"


def _heuristic_summary(post: dict[str, Any], entities: dict[str, Any]) -> StrategySummary:
    title = str(post.get("title", ""))
    return StrategySummary(
        post_id=int(post["post_id"]),
        strategy_type=_infer_strategy_type(title),
        one_line=title[:200],
        factors=[],
        key_params=entities.get("key_params") or {},
        code_dependencies=entities.get("factors_called") or [],
        risk_handling=[],
        backtest_claimed={},
        applicable_market="A 股",
        failure_modes=[],
    )


def _summary_from_post(post: dict[str, Any], entities: dict[str, Any]) -> StrategySummary:
    raw = post.get("summary")
    if isinstance(raw, StrategySummary):
        return raw
    if isinstance(raw, dict) and raw.get("post_id") is not None:
        return StrategySummary.model_validate(raw)
    return _heuristic_summary(post, entities)


def _build_header(layer: StrategyLayer, post: dict[str, Any], extra: str = "") -> str:
    bits = [
        f"[jq_strategy | layer={layer.value} | post_id={post['post_id']}]",
        f"标题: {post.get('title', '')}",
        f"年份: {post.get('year', '')}",
    ]
    if extra:
        bits.append(extra)
    return "\n".join(bits)


def _format_summary_content(summary: StrategySummary) -> str:
    lines = [
        f"策略类型: {summary.strategy_type}",
        f"一句话: {summary.one_line}",
    ]
    if summary.factors:
        lines.append(f"因子: {', '.join(summary.factors)}")
    if summary.code_dependencies:
        lines.append(f"依赖 API: {', '.join(summary.code_dependencies)}")
    if summary.key_params:
        lines.append(
            f"关键参数: {json.dumps(json_safe_value(summary.key_params), ensure_ascii=False)}"
        )
    if summary.risk_handling:
        lines.append(f"风控: {', '.join(summary.risk_handling)}")
    if summary.applicable_market:
        lines.append(f"适用市场: {summary.applicable_market}")
    return "\n".join(lines)


def chunk_jq_strategy_post(post: dict[str, Any]) -> list[JqStrategyChunk]:
    entities = extract_entities(post.get("code") or "")
    summary = _summary_from_post(post, entities)
    chunks: list[JqStrategyChunk] = []
    post_id = int(post["post_id"])
    year = int(post.get("year", 2023))
    title = str(post.get("title", ""))
    author = str(post.get("author", "unknown"))
    source_url = str(post.get("source_url") or "")

    summary_body = _format_summary_content(summary)
    summary_header = _build_header(StrategyLayer.SUMMARY, post, f"类型: {summary.strategy_type}")
    chunks.append(
        JqStrategyChunk(
            id=f"strategy::{post_id}::summary",
            post_id=post_id,
            year=year,
            title=title,
            author=author,
            source_url=source_url,
            layer=StrategyLayer.SUMMARY,
            strategy_type=summary.strategy_type,
            content=summary_body,
            contextual_content=f"{summary_header}\n\n{summary_body}",
        )
    )

    seen_entity: set[str] = set()
    seen_code: set[str] = set()
    for api in entities.get("factors_called") or []:
        key = f"api:{api}"
        if key in seen_entity:
            continue
        seen_entity.add(key)
        body = f"策略《{title}》使用 API: {api}"
        chunks.append(
            JqStrategyChunk(
                id=f"strategy::{post_id}::api::{api}",
                post_id=post_id,
                year=year,
                title=title,
                author=author,
                source_url=source_url,
                layer=StrategyLayer.ENTITY,
                entity_type="api",
                entity_name=api,
                strategy_type=summary.strategy_type,
                content=body,
                contextual_content=f"{_build_header(StrategyLayer.ENTITY, post, f'API: {api}')}\n\n{body}",
            )
        )

    for factor in summary.factors:
        key = f"factor:{factor}"
        if key in seen_entity:
            continue
        seen_entity.add(key)
        body = f"策略《{title}》涉及因子: {factor}"
        chunks.append(
            JqStrategyChunk(
                id=f"strategy::{post_id}::factor::{re.sub(r'[^\\w.-]', '_', factor)}",
                post_id=post_id,
                year=year,
                title=title,
                author=author,
                source_url=source_url,
                layer=StrategyLayer.ENTITY,
                entity_type="factor",
                entity_name=factor,
                strategy_type=summary.strategy_type,
                content=body,
                contextual_content=f"{_build_header(StrategyLayer.ENTITY, post, f'因子: {factor}')}\n\n{body}",
            )
        )

    for func_name in entities.get("functions") or []:
        if func_name in seen_code:
            continue
        seen_code.add(func_name)
        func_code = extract_function_code(post.get("code") or "", func_name)
        if not func_code:
            continue
        body = func_code[:4000]
        chunks.append(
            JqStrategyChunk(
                id=f"strategy::{post_id}::code::{func_name}",
                post_id=post_id,
                year=year,
                title=title,
                author=author,
                source_url=source_url,
                layer=StrategyLayer.CODE,
                function_name=func_name,
                strategy_type=summary.strategy_type,
                content=body,
                contextual_content=(
                    f"{_build_header(StrategyLayer.CODE, post, f'函数: {func_name}')}\n\n{body}"
                ),
            )
        )

    return chunks


def chunk_jq_strategy_posts(posts: list[dict[str, Any]]) -> list[JqStrategyChunk]:
    deduped = _dedupe_posts_by_id(posts)
    chunks: list[JqStrategyChunk] = []
    total = len(deduped)
    logger.info("Chunking %d jq_strategy posts...", total)
    for i, post in enumerate(deduped, 1):
        if i == 1 or i % 50 == 0 or i == total:
            logger.info("Chunking progress %d/%d", i, total)
        chunks.extend(chunk_jq_strategy_post(post))
    logger.info("Chunked %d posts → %d chunks", total, len(chunks))
    return chunks


def _dedupe_posts_by_id(posts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Reassign post_id when the same id appears with different titles (bad clone headers)."""
    from app.core.jq_kb.parser.strategy_txt import stable_hash

    seen: dict[int, str] = {}
    out: list[dict[str, Any]] = []
    for post in posts:
        row = dict(post)
        pid = int(row["post_id"])
        title = str(row.get("title", ""))
        if pid in seen and seen[pid] != title:
            source = str(row.get("source_file") or title)
            row["post_id"] = stable_hash(source)
        else:
            seen[pid] = title
        out.append(row)
    return out
