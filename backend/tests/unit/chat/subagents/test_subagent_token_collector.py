"""Tests for SubagentTokenCollector — per-subagent LLM usage capture.

Ports deer-flow's subagents/token_collector.py:16-72:
- BaseCallbackHandler.on_llm_end captures usage_metadata from each generation
- Dedup by run_id so re-entrant on_llm_end calls collapse to one record
"""

from __future__ import annotations

from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, LLMResult

from app.core.chat.subagents.token_collector import SubagentTokenCollector


def _make_llm_result(usage: dict[str, int] | None, model_name: str = "subagent-model") -> LLMResult:
    """Build a synthetic LLMResult with one ``ChatGeneration`` carrying usage."""
    msg = AIMessage(content="")
    msg.usage_metadata = usage  # type: ignore[attr-defined]
    msg.response_metadata = {"model_name": model_name}
    gen = ChatGeneration(message=msg, text="")
    return LLMResult(generations=[[gen]])


def test_collects_usage_metadata() -> None:
    collector = SubagentTokenCollector(caller="subagent:test")
    result = _make_llm_result({"input_tokens": 11, "output_tokens": 7, "total_tokens": 18})
    collector.on_llm_end(result, run_id="run-A")

    records = collector.snapshot_records()
    assert len(records) == 1
    rec = records[0]
    assert rec["caller"] == "subagent:test"
    assert rec["source_run_id"] == "run-A"
    assert rec["model_name"] == "subagent-model"
    assert rec["input_tokens"] == 11
    assert rec["output_tokens"] == 7
    assert rec["total_tokens"] == 18


def test_dedups_by_run_id() -> None:
    collector = SubagentTokenCollector(caller="subagent:test")
    result = _make_llm_result({"input_tokens": 5, "output_tokens": 5, "total_tokens": 10})

    # Same run_id re-fired should not double-count
    collector.on_llm_end(result, run_id="run-X")
    collector.on_llm_end(result, run_id="run-X")
    collector.on_llm_end(result, run_id="run-Y")

    records = collector.snapshot_records()
    assert len(records) == 2
    run_ids = {r["source_run_id"] for r in records}
    assert run_ids == {"run-X", "run-Y"}


def test_ignores_zero_token_generations() -> None:
    collector = SubagentTokenCollector(caller="subagent:test")
    empty = _make_llm_result({"input_tokens": 0, "output_tokens": 0, "total_tokens": 0})
    collector.on_llm_end(empty, run_id="run-zero")
    assert collector.snapshot_records() == []


def test_snapshot_returns_copy() -> None:
    collector = SubagentTokenCollector(caller="subagent:test")
    result = _make_llm_result({"input_tokens": 1, "output_tokens": 1, "total_tokens": 2})
    collector.on_llm_end(result, run_id="run-snap")
    snap = collector.snapshot_records()
    snap.clear()
    assert len(collector.snapshot_records()) == 1
