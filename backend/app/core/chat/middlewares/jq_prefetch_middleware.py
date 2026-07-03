"""JqPrefetchMiddleware — pre-model injection of jq_kb docs via shortcuts.

Cooperates with :class:`DynamicContextMiddleware` (which runs before this in
the chain). After DynamicContext has id-swapped the user HumanMessage into a
``__user``-suffixed message, this middleware:

1. Scans the latest ``__user`` message for jq_kb-relevant signals: API
   function names (``get_price``, ``order_target``…), industry / concept /
   index / suffix codes (``HY001``, ``GN003``, ``000300``, ``.XSHG``, …), and
   market-field names (``close``, ``pe_ratio``, …).
2. Triggers the metadata-exact-match retriever shortcuts
   (:meth:`JqApiRetriever.retrieve_by_function_name` /
   :meth:`JqDictRetriever.retrieve_by_code`) in parallel. These are
   metadata-filter lookups — no LLM query rewriting, no embedding round-trip,
   millisecond latency. ``search_jq_strategy`` is intentionally skipped: it
   has no metadata shortcut (full hybrid only) and would defeat the purpose.
3. If at least one hit is returned, injects a hidden
   ``HumanMessage(id='{user_id}__jqref', hide_from_ui=True)`` immediately
   AFTER the latest ``__user`` message carrying the formatted docs.

The model "sees" the jq source text in-context, so for simple API / field
queries it does not need to call ``search_jq_*`` at all — eliminating one
LLM-tool round-trip and roughly halving first-token latency on those turns.

This complements (does not replace) the active-tool path:
``ToolOutputBudgetMiddleware`` bounds the size of
``ToolMessage`` results from calls the model still chooses to make;
``ToolErrorHandlingMiddleware`` keeps the run alive when those calls fail.

The ``__jqref`` suffix mirrors DynamicContext's ``__user`` / ``__memory``
suffix convention. DynamicContext's ``_is_user_injection_target`` is
extended to also skip ``__jqref`` so a re-injection pass cannot grow the
suffix (``__jqref__jqref``…) or treat a jqref block as a fresh user turn.

Deduplication across turns: the middleware skips prefetch when a
``__jqref`` message with the same target's id prefix is already present in
state. ``Command`` promotion semantics (deer-flow ``tool_search``) are NOT
used — this is pure context injection, not deferred-tool schema fetching.
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from typing import Any, override

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import BaseMessage, HumanMessage
from langgraph.runtime import Runtime

logger = logging.getLogger(__name__)

# Suffix on HumanMessage.id marking a jqref injection block. Mirrors
# DynamicContext's __user / __memory suffix convention.
_JQREF_SUFFIX = "__jqref"

# Cap the number of prefetched signals so a noisy message cannot inflate
# context with too many docs at once. Two per (kind, key-group) is enough:
# the model rarely needs more than two API/field references per turn.
MAX_SIGNALS = 6

# Field/field-like dict codes worth retrieving without an explicit HY/GN
# prefix. Matched as whole-word identifiers so they do NOT trigger on
# substrings (e.g. "enclose" should not match "close").
_MARKET_FIELD_CODES = frozenset(
    {
        "close",
        "open",
        "high",
        "low",
        "volume",
        "money",
        "pe_ratio",
        "pb_ratio",
        "turnover_ratio",
        "pre_close",
        "high_limit",
        "low_limit",
        "avg",
        "factor",
        "money_flow",
    }
)

# API function names — common verbs in JQ. Whole-word boundary + lower.
# The captured name extends to lowercase letters / underscores/digits.
_API_FUNCTION_RE = re.compile(
    r"\b((?:get|set|order|run|create|history|attribute_history|current_price|"
    r"get_price|order_target|order_value|set_order_cost|set_slippage|"
    r"set_option|set_subportfolios|before_trading|after_trading|handle_data|"
    r"initialize|after_code_changed|process_initialize|on_strategy_end|"
    r"run_before_trading|run_daily|run_weekly|run_monthly|"
    r"get_fundamentals|get_factor|get_ticks|get_snapshot|get_billboard_list|"
    r"get_index_stocks|get_industry|get_concept|get_security_info|"
    r"get_all_securities|get_extras|get_bars|get_current_tick|"
    r"get_dividend_factors|get_money_flow|get_locked_positions|"
    r"get_mtss|get_fundamentals_continuously|get_factor_values|"
    r"set_universe|set_benchmark|set_commission|"
    r"transfer_balance|withdraw_cash|deposit_cash|"
    r"log|record|record_metric|plot|"
    r"get_trades|get_orders|get_positions|get_portfolio|get_account|"
    r"cancel_order|cancel_all_orders|"
    r"get_locked_security|get_locked_stocks|"
    r"run_after_trading|set_global_context|get_global_context|"
    r"get_locked_position_subaccounts|get_locked_position|"
    r"[a-z_]+_ratio|[a-z_]+_factor|attribute_history)[a-z_]*)\b"
)

# Industry / concept / index codes.
_CODE_PATTERNS = [
    (re.compile(r"\b(HY\d{3,4})\b"), "HY"),  # industry HY001...
    (re.compile(r"\b(GN\d{3,4})\b"), "GN"),  # concept GN003...
    (re.compile(r"\b(399\d{3})\b"), "INDEX"),  # Shenzhen index 399001
    (re.compile(r"\b(000\d{3})\b"), "INDEX"),  # Shanghai index 000300
]

# Code suffix tokens. The leading dot is a non-word char so ``\b`` cannot
# anchor it; anchor on the preceding space / start-of-string instead.
_SUFFIX_RE = re.compile(r"(?<![\w.])(\.(?:XSHG|XSHE))\b")

_MARKET_FIELD_RE = re.compile(r"\b(" + "|".join(re.escape(f) for f in _MARKET_FIELD_CODES) + r")\b")

# HumanMessage additional_kwargs marker used to detect a jqref block.
_JQREF_KWARG = "jqref"


@dataclass(frozen=True)
class _Signal:
    """A detected jq_kb-relevant token in the user message."""

    kind: str  # "api" | "dict"
    key: str  # canonical lookup key (function name or code)


def _dedup_signals(signals: list[_Signal]) -> list[_Signal]:
    """Preserve first-occurrence order, drop duplicates of (kind, key)."""
    seen: set[tuple[str, str]] = set()
    out: list[_Signal] = []
    for s in signals:
        if (s.kind, s.key) in seen:
            continue
        seen.add((s.kind, s.key))
        out.append(s)
    return out


def _extract_jq_signals(text: str) -> list[_Signal]:
    """Extract jq_kb lookup signals from user text, capped at MAX_SIGNALS.

    The result is ordered by signal kind (api first, then dict) so that when
    more than MAX_SIGNALS match, the most-relevant kinds survive the cap.
    """
    if not text:
        return []

    raw_api: list[_Signal] = []
    for m in _API_FUNCTION_RE.finditer(text):
        name = m.group(1).lower()
        # Strip common false positives: bare "log"/"open"/"high"/"low" may
        # bleed in from the regex alternation; keep them only when they look
        # like a function (contain "_" or are explicitly function-shaped).
        if name in {"log", "open", "high", "low", "money", "avg", "factor"}:
            # These collide with market fields; treat them as fields, not APIs.
            continue
        raw_api.append(_Signal("api", name))

    raw_dict: list[_Signal] = []
    for rx, _tag in _CODE_PATTERNS:
        for m in rx.finditer(text):
            raw_dict.append(_Signal("dict", m.group(1)))
    for m in _SUFFIX_RE.finditer(text):
        raw_dict.append(_Signal("dict", m.group(1)))
    for m in _MARKET_FIELD_RE.finditer(text):
        raw_dict.append(_Signal("dict", m.group(1)))

    api = _dedup_signals(raw_api)
    dict_s = _dedup_signals(raw_dict)
    # Budget: take up to MAX_SIGNALS // 2 of each kind so a message full of
    # API names doesn't starve dict lookups (and vice versa).
    per_kind = MAX_SIGNALS // 2
    api = api[:per_kind]
    dict_s = dict_s[:per_kind]
    return _dedup_signals(api + dict_s)[:MAX_SIGNALS]


def _format_jqref_block(api_hits: list[Any], dict_hits: list[Any]) -> str:
    """Format retrieved chunks into a ``<jqref>`` injection block.

    Returns ``""`` when neither list has any hit, so the caller can decide
    whether to inject at all (no injection when there is nothing to inject).
    """
    if not api_hits and not dict_hits:
        return ""

    parts: list[str] = [
        "<jqref> 下面是已检索到的聚宽 API / 数据字典原文，可直接参考，无需重复调用 search_jq_*："
    ]

    if api_hits:
        parts.append("## 聚宽 API 文档")
        for i, hit in enumerate(api_hits, 1):
            meta = getattr(hit, "metadata", {}) or {}
            fn = meta.get("function_name", getattr(hit, "chunk_id", "?"))
            url = meta.get("source_url", "")
            body = (hit.document or "")[:1500]
            parts.append(f"### {i}. {fn}\n来源: {url}\n{body}")

    if dict_hits:
        parts.append("## 聚宽数据字典")
        for i, hit in enumerate(dict_hits, 1):
            meta = getattr(hit, "metadata", {}) or {}
            code = meta.get("code", getattr(hit, "chunk_id", "?"))
            name = meta.get("name", "")
            dtype = meta.get("dict_type", "")
            body = (hit.document or "")[:1500]
            parts.append(f"### {i}. {code} {name} ({dtype})\n{body}")

    parts.append("</jqref>")
    return "\n\n".join(parts)


def _last_user_message(messages: list[BaseMessage]) -> tuple[int, HumanMessage] | None:
    """Return (index, latest __user-suffixed HumanMessage) or None.

    Only messages whose id ends with ``__user`` (DynamicContext's id-swap
    marker) are candidates — bare HumanMessages are the pre-first-turn form
    and are skipped because DynamicContext runs BEFORE this middleware and
    would have transformed them already.
    """
    for idx in range(len(messages) - 1, -1, -1):
        m = messages[idx]
        if not isinstance(m, HumanMessage):
            continue
        mid = str(m.id) if m.id else ""
        if mid.endswith("__user"):
            return idx, m
    return None


def _target_jqref_id(user_msg: HumanMessage) -> str:
    """Build the jqref HumanMessage id for a given user message."""
    base = str(user_msg.id)
    # user_msg.id already ends with __user; strip it and append __jqref so
    # multiple jqref blocks for the same user turn are idempotent.
    stem = base[: -len("__user")] if base.endswith("__user") else base
    return f"{stem}{_JQREF_SUFFIX}"


def _has_jqref_for(messages: list[BaseMessage], target_jqref_id: str) -> bool:
    """True if a jqref block with *target_jqref_id* already exists in state."""
    for m in messages:
        if not isinstance(m, HumanMessage):
            continue
        if str(getattr(m, "id", "")) == target_jqref_id:
            return True
    return False


class JqPrefetchMiddleware(AgentMiddleware[AgentState]):
    """Inject jq_kb docs into context before the model call.

    Args:
        api_retriever: JqApiRetriever instance (or any object exposing
            ``async retrieve_by_function_name(name)``). When None, the
            module-level singleton from ``jq_kb.tools`` is loaded lazily on
            first use.
        dict_retriever: JqDictRetriever instance (or any object exposing
            ``async retrieve_by_code(code)``). Lazy singleton when None.
        max_signals: Override cap on detected signals (default MAX_SIGNALS).
            Kept as a constructor arg so tests can raise the cap for the
            "many distinct signals" boundary case.
    """

    def __init__(
        self,
        *,
        api_retriever: Any = None,
        dict_retriever: Any = None,
        max_signals: int = MAX_SIGNALS,
    ) -> None:
        self._api_retriever = api_retriever
        self._dict_retriever = dict_retriever
        self._max_signals = max_signals

    # -- lazy singleton loaders ---------------------------------------------

    def _resolve_api(self) -> Any:
        if self._api_retriever is None:
            from app.core.jq_kb.tools import _get_jq_api_retriever

            self._api_retriever = _get_jq_api_retriever()
        return self._api_retriever

    def _resolve_dict(self) -> Any:
        if self._dict_retriever is None:
            from app.core.jq_kb.tools import _get_jq_dict_retriever

            self._dict_retriever = _get_jq_dict_retriever()
        return self._dict_retriever

    # -- hook ---------------------------------------------------------------

    @override
    async def abefore_model(self, state: AgentState, runtime: Runtime) -> dict[str, Any] | None:
        messages: list[BaseMessage] = list(state.get("messages", []))
        if not messages:
            return None

        found = _last_user_message(messages)
        if found is None:
            return None
        user_idx, user_msg = found

        jqref_id = _target_jqref_id(user_msg)
        if _has_jqref_for(messages, jqref_id):
            # Already prefetched this turn — idempotent skip.
            return None

        text = _as_text(user_msg.content)
        if not text:
            return None

        signals = _extract_jq_signals(text)
        if not signals:
            return None

        api_keys = [s.key for s in signals if s.kind == "api"]
        dict_keys = [s.key for s in signals if s.kind == "dict"]
        if not api_keys and not dict_keys:
            return None

        api_retriever = self._resolve_api() if api_keys else None
        dict_retriever = self._resolve_dict() if dict_keys else None

        api_hits, dict_hits = await _parallel_fetch(
            api_retriever=api_retriever,
            api_keys=api_keys,
            dict_retriever=dict_retriever,
            dict_keys=dict_keys,
        )

        block = _format_jqref_block(api_hits, dict_hits)
        if not block:
            return None

        injected = HumanMessage(
            content=block,
            id=jqref_id,
            additional_kwargs={_JQREF_KWARG: True, "hide_from_ui": True},
        )
        new_messages = list(messages)
        new_messages.insert(user_idx + 1, injected)
        return {"messages": new_messages}


def _as_text(content: Any) -> str:
    """Extract a flat text view from a HumanMessage content shape."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        out: list[str] = []
        for part in content:
            if isinstance(part, str):
                out.append(part)
            elif isinstance(part, dict) and isinstance(part.get("text"), str):
                out.append(part["text"])
        return " ".join(out)
    return str(content)


async def _parallel_fetch(
    *,
    api_retriever: Any,
    api_keys: list[str],
    dict_retriever: Any,
    dict_keys: list[str],
) -> tuple[list[Any], list[Any]]:
    """Run api / dict metadata shortcuts concurrently and collect hits.

    Per-key failures are swallowed (logged) so a single shortcut failure does
    not abort the whole prefetch — failure means "no doc for this key", not
    "abort the turn". All api + dict shortcuts run in ONE ``asyncio.gather``
    so the api and dict retrievers actually execute concurrently rather than
    in two separate waves.
    """
    api_tasks: list[Any] = []
    if api_retriever is not None:
        for key in api_keys:
            api_tasks.append(_safe_call(api_retriever.retrieve_by_function_name, key))

    dict_tasks: list[Any] = []
    if dict_retriever is not None:
        for key in dict_keys:
            dict_tasks.append(_safe_call(dict_retriever.retrieve_by_code, key))

    all_results = await asyncio.gather(*api_tasks, *dict_tasks) if (api_tasks or dict_tasks) else []
    api_results = all_results[: len(api_tasks)]
    dict_results = all_results[len(api_tasks) :]
    api_hits = [r for r in api_results if r is not None]
    dict_hits = [r for r in dict_results if r is not None]
    return api_hits, dict_hits


async def _safe_call(fn: Any, *args: Any) -> Any:
    """Call an async function, swallow exceptions, return None on failure."""
    try:
        return await fn(*args)
    except Exception:
        logger.warning("jqref prefetch shortcut call failed: %s", args, exc_info=True)
        return None
