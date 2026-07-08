"""Tests for JqPrefetchMiddleware.

Verifies that the middleware:
1. Scans the latest user message for jq_kb-relevant signals (API function
   names, industry/concept codes, indices, code suffixes, market fields).
2. Triggers the metadata-exact-match retriever shortcuts (no LLM, no
   embedding) in parallel for the detected signals.
3. Injects the matched docs as a hidden ``HumanMessage(id='{user_id}__jqref')``
   so the model already sees the source text and does not need to call
   ``search_jq_*``.
4. Skip cases: no signals in the user message; jqref already injected for
   the same target id; non-jq conversation; no retriever hits.

The retriever calls are mocked — these tests exercise wiring and message
shape, not the Chroma/HTTP stack.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain.agents import AgentState
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.runtime import Runtime

from app.core.chat.middlewares.jq_prefetch_middleware import (
    _JQREF_SUFFIX,
    MAX_SIGNALS,
    JqPrefetchMiddleware,
    _extract_jq_signals,
    _format_jqref_block,
)


class TestExtractJqSignals:
    def test_api_function_get_price(self) -> None:
        sigs = _extract_jq_signals("用 get_price 取最近 30 天数据")
        assert any(s.kind == "api" and s.key == "get_price" for s in sigs)

    def test_api_function_order_target(self) -> None:
        sigs = _extract_jq_signals("调用 order_target_value 把持仓调到 1000")
        assert any(s.kind == "api" and s.key == "order_target_value" for s in sigs)

    def test_industry_code_hy(self) -> None:
        sigs = _extract_jq_signals("HY001 是什么行业")
        assert any(s.kind == "dict" and s.key == "HY001" for s in sigs)

    def test_concept_code_gn(self) -> None:
        sigs = _extract_jq_signals("人工智能概念 GN003")
        assert any(s.kind == "dict" and s.key == "GN003" for s in sigs)

    def test_index_code_000300(self) -> None:
        sigs = _extract_jq_signals("沪深300 是 000300 吗")
        assert any(s.kind == "dict" and s.key == "000300" for s in sigs)

    def test_code_suffix_xshg(self) -> None:
        sigs = _extract_jq_signals(".XSHG 是上交所吗")
        assert any(s.kind == "dict" and s.key == ".XSHG" for s in sigs)

    def test_market_field_close(self) -> None:
        sigs = _extract_jq_signals("close 字段是什么含义")
        assert any(s.kind == "dict" and s.key == "close" for s in sigs)

    def test_market_field_pe_ratio(self) -> None:
        sigs = _extract_jq_signals("pe_ratio 单位是多少")
        assert any(s.kind == "dict" and s.key == "pe_ratio" for s in sigs)

    def test_no_signals_returns_empty(self) -> None:
        assert _extract_jq_signals("今天天气怎么样") == []

    def test_dedup_same_signal_once(self) -> None:
        sigs = _extract_jq_signals("get_price 还是 get_price")
        api_sigs = [s for s in sigs if s.kind == "api"]
        assert len(api_sigs) == 1
        assert api_sigs[0].key == "get_price"

    def test_max_signals_cap(self) -> None:
        # Many distinct signals — must be bounded by MAX_SIGNALS=6 to avoid
        # inflating context with too many prefetched docs. Per-kind cap is
        # MAX_SIGNALS // 2 = 3, so a signal-heavy message that mixes api and
        # dict kinds can reach up to 6; a single-kind burst is capped at 3.
        text = " ".join(f"get_{i}_x" for i in range(20))
        text += " HY001 HY002 HY003 HY004 HY005 HY006"
        sigs = _extract_jq_signals(text)
        assert len(sigs) <= MAX_SIGNALS


class TestFormatJqrefBlock:
    def test_empty_hits_returns_empty_string(self) -> None:
        api_hits: list[Any] = []
        dict_hits: list[Any] = []
        assert _format_jqref_block(api_hits, dict_hits) == ""

    def test_api_only_hit(self) -> None:
        api_hits = [
            MagicMock(
                metadata={"function_name": "get_price", "source_url": "u"},
                document="doc1",
                score=1.0,
                chunk_id="c1",
            )
        ]
        block = _format_jqref_block(api_hits, [])
        assert "<jqref>" in block
        assert "</jqref>" in block
        assert "get_price" in block
        assert "doc1" in block

    def test_dict_only_hit(self) -> None:
        dict_hits = [
            MagicMock(
                metadata={"code": "HY001", "name": "农林牧渔", "dict_type": "行业"},
                document="doc2",
                score=1.0,
                chunk_id="c2",
            )
        ]
        block = _format_jqref_block([], dict_hits)
        assert "<jqref>" in block
        assert "HY001" in block
        assert "doc2" in block

    def test_both_hits(self) -> None:
        api_hits = [
            MagicMock(
                metadata={"function_name": "get_price", "source_url": ""},
                document="a",
                score=1.0,
                chunk_id="ca",
            )
        ]
        dict_hits = [
            MagicMock(
                metadata={"code": "close", "name": "收盘价", "dict_type": "字段"},
                document="d",
                score=1.0,
                chunk_id="cd",
            )
        ]
        block = _format_jqref_block(api_hits, dict_hits)
        assert "<jqref>" in block
        assert "get_price" in block
        assert "close" in block


def _state_with_user(content: str, *, user_id: str = "u1") -> AgentState:
    """Build an AgentState with one user HumanMessage already id-swapped."""
    return {
        "messages": [
            SystemMessage(
                content="reminder",
                id=user_id,
                additional_kwargs={"dynamic_context_reminder": True, "reminder_date": "x"},
            ),
            HumanMessage(
                content=content,
                id=f"{user_id}__user",
                additional_kwargs={},
            ),
        ]
    }


def _make_runtime() -> Any:
    return MagicMock(spec=Runtime)


@pytest.fixture
def retriever_bundle() -> tuple[MagicMock, MagicMock]:
    """Return (api_retriever, dict_retriever) async mocks."""
    api = MagicMock()
    api.retrieve_by_function_name = AsyncMock(return_value=None)
    dict_r = MagicMock()
    dict_r.retrieve_by_code = AsyncMock(return_value=None)
    return api, dict_r


class TestMiddlewareHook:
    async def test_injects_jqref_when_api_function_detected(
        self, retriever_bundle: tuple[MagicMock, MagicMock]
    ) -> None:
        api, dict_r = retriever_bundle
        api.retrieve_by_function_name.return_value = MagicMock(
            metadata={"function_name": "get_price", "source_url": "u"},
            document="get_price 签名 ...",
            score=1.0,
            chunk_id="api1",
        )
        mw = JqPrefetchMiddleware(api_retriever=api, dict_retriever=dict_r, max_signals=6)

        state = _state_with_user("get_price 怎么用")
        result = await mw.abefore_model(state, _make_runtime())

        assert result is not None
        msgs = result["messages"]
        assert len(msgs) == 3  # system + __user + injected __jqref
        injected = msgs[-1]
        assert isinstance(injected, HumanMessage)
        assert injected.id and injected.id.endswith(_JQREF_SUFFIX)
        assert injected.additional_kwargs.get("hide_from_ui") is True
        assert "get_price" in injected.content

    async def test_no_signals_returns_none(
        self, retriever_bundle: tuple[MagicMock, MagicMock]
    ) -> None:
        api, dict_r = retriever_bundle
        mw = JqPrefetchMiddleware(api_retriever=api, dict_retriever=dict_r)
        state = _state_with_user("你好天气如何")
        result = await mw.abefore_model(state, _make_runtime())
        assert result is None
        api.retrieve_by_function_name.assert_not_called()

    async def test_already_injected_jqref_skips(
        self, retriever_bundle: tuple[MagicMock, MagicMock]
    ) -> None:
        api, dict_r = retriever_bundle
        mw = JqPrefetchMiddleware(api_retriever=api, dict_retriever=dict_r)
        state: AgentState = {
            "messages": [
                SystemMessage(
                    content="r",
                    id="u1",
                    additional_kwargs={"dynamic_context_reminder": True, "reminder_date": "x"},
                ),
                HumanMessage(content="get_price 怎么用", id="u1__user"),
                HumanMessage(
                    content="prev jqref", id="u1__jqref", additional_kwargs={"hide_from_ui": True}
                ),
            ]
        }
        result = await mw.abefore_model(state, _make_runtime())
        assert result is None
        api.retrieve_by_function_name.assert_not_called()

    async def test_no_user_message_returns_none(
        self, retriever_bundle: tuple[MagicMock, MagicMock]
    ) -> None:
        api, dict_r = retriever_bundle
        mw = JqPrefetchMiddleware(api_retriever=api, dict_retriever=dict_r)
        state: AgentState = {"messages": [SystemMessage(content="sys")]}
        result = await mw.abefore_model(state, _make_runtime())
        assert result is None

    async def test_no_hit_returns_none(self, retriever_bundle: tuple[MagicMock, MagicMock]) -> None:
        api, dict_r = retriever_bundle
        # retrieve_by_function_name returns None (no metadata match)
        mw = JqPrefetchMiddleware(api_retriever=api, dict_retriever=dict_r)
        state = _state_with_user("get_price 怎么用")
        result = await mw.abefore_model(state, _make_runtime())
        assert result is None  # nothing to inject

    async def test_dict_signal_triggers_dict_shortcut(
        self, retriever_bundle: tuple[MagicMock, MagicMock]
    ) -> None:
        api, dict_r = retriever_bundle
        dict_r.retrieve_by_code.return_value = MagicMock(
            metadata={"code": "HY001", "name": "农林牧渔", "dict_type": "行业"},
            document="HY001 农林牧渔 ...",
            score=1.0,
            chunk_id="d1",
        )
        mw = JqPrefetchMiddleware(api_retriever=api, dict_retriever=dict_r)
        state = _state_with_user("HY001 是什么行业")
        result = await mw.abefore_model(state, _make_runtime())
        assert result is not None
        dict_r.retrieve_by_code.assert_awaited_once_with("HY001")
        api.retrieve_by_function_name.assert_not_called()
        assert "HY001" in result["messages"][-1].content

    async def test_parallel_both_signals(
        self, retriever_bundle: tuple[MagicMock, MagicMock]
    ) -> None:
        api, dict_r = retriever_bundle
        api.retrieve_by_function_name.return_value = MagicMock(
            metadata={"function_name": "get_price", "source_url": ""},
            document="api-doc",
            score=1.0,
            chunk_id="a1",
        )
        dict_r.retrieve_by_code.return_value = MagicMock(
            metadata={"code": "close", "name": "收盘价", "dict_type": "字段"},
            document="close 收盘价",
            score=1.0,
            chunk_id="d2",
        )
        mw = JqPrefetchMiddleware(api_retriever=api, dict_retriever=dict_r)
        state = _state_with_user("get_price 的 close 字段")
        # Confirm both shortcuts fire exactly once for their respective signals
        result = await mw.abefore_model(state, _make_runtime())
        assert result is not None
        api.retrieve_by_function_name.assert_awaited_once_with("get_price")
        dict_r.retrieve_by_code.assert_awaited_once_with("close")
