"""LLM 8-dim summaries for jq_strategy (resumable via summaries.jsonl)."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
import sys
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.core.jq_kb.ast_parser import extract_entities
from app.core.jq_kb.cli_logging import configure_cli_logging
from app.core.jq_kb.paths import JQ_STRATEGY_RAW_DIR, JQ_STRATEGY_SUMMARIES_PATH
from app.core.jq_kb.schemas import StrategySummary
from app.settings import get_settings

logger = logging.getLogger(__name__)

SUMMARY_SYSTEM = """你是量化策略分析专家。根据聚宽策略源码生成结构化摘要。
严格只输出一个 JSON 对象（不要 markdown 代码块、不要解释、不要 <think> 块），
字段及类型:
  strategy_type: string (例如 "多因子 / ETF轮动 / 趋势跟踪 / 套利 / 其他")
  one_line: string (一句话总结)
  factors: string[]
  key_params: object (key=参数名, value=参数值或数字)
  code_dependencies: string[] (聚宽API名)
  risk_handling: string[]
  backtest_claimed: object (key=指标名, value=数字或字符串)
  applicable_market: string (例如 "A 股" / "A 股 ETF" / "商品期货")
  failure_modes: string[]
未识别的字段一律用空字符串、空数组或空对象。"""


def _get_summarize_llm() -> ChatOpenAI:
    settings = get_settings()
    return ChatOpenAI(
        model=settings.model,
        api_key=settings.openai_api_key.get_secret_value(),  # type: ignore[arg-type]
        base_url=settings.openai_base_url,
        temperature=0.0,
    )


_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_CHANNEL_TAG_RE = re.compile(r"<\|/?[a-zA-Z_]+\|?>")
_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def _clean_response(raw: str) -> str:
    text = _THINK_RE.sub("", raw.strip())
    text = _CHANNEL_TAG_RE.sub("", text)
    return _FENCE_RE.sub("", text).strip()


def _find_json_objects(text: str) -> list[dict[str, Any]]:
    """Return all top-level JSON objects in ``text`` (resilient to narration)."""
    decoder = json.JSONDecoder()
    objects: list[dict[str, Any]] = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch != "{":
            i += 1
            continue
        try:
            obj, end = decoder.raw_decode(text, i)
        except json.JSONDecodeError:
            i += 1
            continue
        if isinstance(obj, dict):
            objects.append(obj)
        i = max(end, i + 1)
    return objects


def _to_str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value if v is not None and str(v).strip()]
    if isinstance(value, str):
        if not value.strip():
            return []
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return [value]
        if isinstance(parsed, list):
            return [str(v) for v in parsed if v is not None and str(v).strip()]
        return [value]
    return [str(value)]


def _to_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "; ".join(_to_str(v) for v in value if v is not None)
    if isinstance(value, dict):
        parts = [f"{k}={_to_str(v)}" for k, v in value.items()]
        return "; ".join(parts)
    return str(value)


def _to_str_dict(value: Any) -> dict[str, str]:
    out: dict[str, str] = {}
    if value is None:
        return out
    if isinstance(value, dict):
        for k, v in value.items():
            key = str(k).strip()
            if not key:
                continue
            if isinstance(v, dict):
                v = "; ".join(f"{kk}={_to_str(vv)}" for kk, vv in v.items())
            elif isinstance(v, list):
                v = "; ".join(_to_str(x) for x in v)
            elif v is None:
                v = ""
            else:
                v = str(v)
            if v == "":
                continue
            out[key] = v
        return out
    if isinstance(value, str):
        if not value.strip():
            return out
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {"value": value}
        if isinstance(parsed, dict):
            return _to_str_dict(parsed)
    return {"value": _to_str(value)}


def _coerce_summary_data(data: dict[str, Any], post_id: int) -> dict[str, Any]:
    out: dict[str, Any] = dict(data)
    out["post_id"] = post_id
    out["strategy_type"] = _to_str(out.get("strategy_type")) or "其他"
    out["one_line"] = _to_str(out.get("one_line"))
    out["factors"] = _to_str_list(out.get("factors"))
    out["key_params"] = _to_str_dict(out.get("key_params"))
    out["code_dependencies"] = _to_str_list(out.get("code_dependencies"))
    out["risk_handling"] = _to_str_list(out.get("risk_handling"))
    out["backtest_claimed"] = _to_str_dict(out.get("backtest_claimed"))
    out["applicable_market"] = _to_str(out.get("applicable_market")) or "A 股"
    out["failure_modes"] = _to_str_list(out.get("failure_modes"))
    return out


def _heuristic_summary(post: dict[str, Any], entities: dict[str, Any]) -> StrategySummary:
    title = str(post.get("title", ""))
    return StrategySummary(
        post_id=int(post["post_id"]),
        strategy_type="其他",
        one_line=title[:200],
        factors=[],
        key_params=entities.get("key_params") or {},
        code_dependencies=entities.get("factors_called") or [],
        risk_handling=[],
        backtest_claimed={},
        applicable_market="A 股",
        failure_modes=[],
    )


def _parse_summary(raw: str, post_id: int) -> StrategySummary:
    text = _clean_response(raw)
    candidates = _find_json_objects(text)
    if not candidates:
        raise ValueError(f"No JSON object found in LLM response (head={text[:200]!r})")
    chosen = max(
        candidates,
        key=lambda d: sum(1 for k in StrategySummary.model_fields if k in d),
    )
    return StrategySummary.model_validate(_coerce_summary_data(chosen, post_id))


async def _summarize_one(post: dict[str, Any], llm: ChatOpenAI, *, retries: int = 2) -> StrategySummary:
    entities = extract_entities(post.get("code") or "")
    prompt = (
        f"post_id={post['post_id']}\n"
        f"标题: {post.get('title')}\n"
        f"年份: {post.get('year')}\n"
        f"函数: {', '.join(entities.get('functions', [])[:20])}\n"
        f"API: {', '.join(entities.get('factors_called', [])[:30])}\n"
        f"关键参数: {json.dumps(entities.get('key_params', {}), ensure_ascii=False)}\n\n"
        f"源码(截断):\n{(post.get('code') or '')[:6000]}"
    )
    last_err: Exception | None = None
    for attempt in range(retries + 1):
        try:
            response = await llm.ainvoke(
                [SystemMessage(content=SUMMARY_SYSTEM), HumanMessage(content=prompt)]
            )
            content = response.content
            if not isinstance(content, str):
                content = str(content)
            return _parse_summary(content, int(post["post_id"]))
        except Exception as exc:
            last_err = exc
            logger.warning(
                "Summarize failed post_id=%s attempt=%d/%d: %s",
                post.get("post_id"),
                attempt + 1,
                retries + 1,
                exc,
            )
    logger.warning(
        "Falling back to heuristic summary for post_id=%s (last_err=%s)",
        post.get("post_id"),
        last_err,
    )
    return _heuristic_summary(post, entities)


def _load_posts(*, pilot: bool) -> list[dict[str, Any]]:
    path = JQ_STRATEGY_RAW_DIR / ("pilot.json" if pilot else "posts.json")
    if not path.is_file():
        path = JQ_STRATEGY_RAW_DIR / "pilot.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    posts: list[dict[str, Any]] = data.get("posts", [])
    return posts


def _load_existing() -> dict[int, dict[str, Any]]:
    if not JQ_STRATEGY_SUMMARIES_PATH.is_file():
        return {}
    out: dict[int, dict[str, Any]] = {}
    for line in JQ_STRATEGY_SUMMARIES_PATH.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            out[int(row["post_id"])] = row
    return out


async def run(
    *,
    pilot: bool,
    limit: int,
    force: bool,
    workers: int,
) -> None:
    posts = _load_posts(pilot=pilot)
    existing = _load_existing() if not force else {}
    pending = [p for p in posts if int(p["post_id"]) not in existing]
    if limit:
        pending = pending[:limit]

    if not pending:
        logger.info(
            "Nothing to do: %d posts, %d summaries already in %s",
            len(posts),
            len(existing),
            JQ_STRATEGY_SUMMARIES_PATH,
        )
        return

    JQ_STRATEGY_SUMMARIES_PATH.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if JQ_STRATEGY_SUMMARIES_PATH.is_file() and not force else "w"
    llm = _get_summarize_llm()
    semaphore = asyncio.Semaphore(max(1, workers))
    write_lock = asyncio.Lock()
    processed = 0
    total = len(pending)

    logger.info(
        "Summarizing %d/%d posts (workers=%d) -> %s",
        total,
        len(posts),
        workers,
        JQ_STRATEGY_SUMMARIES_PATH,
    )

    with open(JQ_STRATEGY_SUMMARIES_PATH, mode, encoding="utf-8") as fh:

        async def _process(post: dict[str, Any]) -> None:
            nonlocal processed
            pid = int(post["post_id"])
            async with semaphore:
                summary = await _summarize_one(post, llm)
            async with write_lock:
                fh.write(summary.model_dump_json(ensure_ascii=False) + "\n")
                fh.flush()
                processed += 1
                if processed == 1 or processed % 10 == 0 or processed == total:
                    logger.info(
                        "Progress %d/%d — post_id=%d (%s)",
                        processed,
                        total,
                        pid,
                        summary.strategy_type,
                    )

        await asyncio.gather(*[_process(post) for post in pending])

    logger.info("Done. wrote %d summaries -> %s", processed, JQ_STRATEGY_SUMMARIES_PATH)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pilot", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    configure_cli_logging()
    asyncio.run(
        run(
            pilot=args.pilot,
            limit=args.limit,
            force=args.force,
            workers=args.workers,
        )
    )


if __name__ == "__main__":
    main()
