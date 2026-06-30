"""Tests for SubagentExecutor.execute_async — real astream/LLM run path.

Asserts that the placeholder echo path is gone and that execute_async drives
a real StateGraph.astream(...) -> get_stream_writer() flow. The model is
mocked at the LangChain ``ChatOpenAI`` boundary so no network is required.

Critical contracts:
- result.result MUST NOT start with "echo:" (echo placeholder removed).
- The real path uses graph.astream(...) (mocked here).
- Stream events tagged by task_id are written via get_stream_writer().
- Token usage is collected via SubagentTokenCollector and reported on the
  SubagentResult.token_usage_records field.
- On cancellation, the run short-circuits to CANCELLED status.
"""

from __future__ import annotations

import asyncio
import inspect
from typing import Any
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import AIMessage

import app.core.chat.subagents.executor as executor_module
from app.core.chat.subagents.executor import (
    SubagentExecutor,
    SubagentStatus,
    _shutdown_isolated_subagent_loop,
    get_background_task_result,
)
from app.core.chat.subagents.token_collector import SubagentTokenCollector


@pytest.fixture(autouse=True)
def _reset_loop() -> None:
    """Ensure a clean isolated loop for every test."""
    _shutdown_isolated_subagent_loop()
    yield
    _shutdown_isolated_subagent_loop()


def _make_fake_graph_with_astream(stream_chunks: list[dict[str, Any]] | None = None) -> MagicMock:
    """Build a mock graph whose astream(...) yields the supplied chunks."""
    graph = MagicMock(name="compiled_subagent_graph")

    async def _astream(state: dict[str, Any], config: Any = None, **_kwargs: Any):
        if stream_chunks is None:
            return
        for chunk in stream_chunks:
            yield chunk

    graph.astream = _astream
    return graph


class _FakeStateGraph:
    """StateGraph stub that returns a configured compiled graph."""

    def __init__(self, compiled: Any) -> None:
        self._compiled = compiled

    def add_node(self, *a: Any, **k: Any) -> None:
        return None

    def set_entry_point(self, *a: Any, **k: Any) -> None:
        return None

    def add_edge(self, *a: Any, **k: Any) -> None:
        return None

    def add_conditional_edges(self, *a: Any, **k: Any) -> None:
        return None

    def compile(self, **_k: Any) -> Any:
        return self._compiled


def test_placeholder_echo_is_removed_from_module_source() -> None:
    """The _aexecute_placeholder and echo: result path are gone."""
    src = inspect.getsource(executor_module)
    assert "_aexecute_placeholder" not in src, "placeholder async body must be removed"
    assert "echo:" not in src, 'placeholder result string "echo:..." must be removed'
    assert "test-placeholder" not in src, "placeholder api_key must be removed"


def test_executor_module_no_longer_exposes_placeholder_helpers() -> None:
    """Module-level helpers that returned echo results must be removed."""
    assert not hasattr(executor_module, "_aexecute_placeholder")
    assert not hasattr(executor_module, "_build_placeholder_subagent")


def test_build_subagent_state_graph_uses_real_chatopenai(monkeypatch: pytest.MonkeyPatch) -> None:
    """The helper used by compile_subagent_graph should resolve a real ChatOpenAI factory.

    The previous placeholder used a hardcoded ``SecretStr("test-placeholder")``;
    the real factory should be injectable so tests can swap in a fake model
    without hitting the network.
    """
    fake_model = MagicMock(name="model")
    captured_kwargs: dict[str, Any] = {}

    def _fake_chat(model: str, **kwargs: Any) -> Any:
        captured_kwargs["model"] = model
        captured_kwargs.update(kwargs)
        return fake_model

    monkeypatch.setattr(executor_module, "ChatOpenAI", _fake_chat)

    _graph, model = executor_module._build_subagent_state_graph("gpt-test")
    assert model is fake_model
    # Model name is resolved from settings, not from the helper arg.
    assert captured_kwargs.get("model") is not None
    # Real factory must NOT hardcode the placeholder api_key
    assert "test-placeholder" not in str(captured_kwargs)


def _wait_for_terminal(task_id: str, timeout: float = 5.0) -> Any:
    """Block until the background task reaches a terminal status."""
    loop = asyncio.new_event_loop()
    try:
        deadline = loop.time() + timeout
        while loop.time() < deadline:
            r = get_background_task_result(task_id)
            if r is not None and r.status.is_terminal:
                return r
            loop.run_until_complete(asyncio.sleep(0.05))
        return get_background_task_result(task_id)
    finally:
        loop.close()


def test_execute_async_drives_real_astream_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """execute_async should drive graph.astream and produce a non-echo result."""
    captured_writes: list[dict[str, Any]] = []

    def _writer(payload: dict[str, Any]) -> None:
        captured_writes.append(payload)

    monkeypatch.setattr(executor_module, "get_stream_writer", lambda: _writer)

    ai_chunk: dict[str, Any] = {"messages": [AIMessage(content="real-subagent-output")]}
    fake_graph = _make_fake_graph_with_astream([ai_chunk])
    monkeypatch.setattr(executor_module, "StateGraph", lambda *a, **kw: _FakeStateGraph(fake_graph))
    monkeypatch.setattr(executor_module, "ChatOpenAI", lambda *a, **kw: MagicMock(name="model"))

    executor = SubagentExecutor(name="general-purpose", prompt="do the thing", timeout_seconds=30)

    task_id = executor.execute_async("do the thing", task_id="task-A")
    result = _wait_for_terminal(task_id)

    assert result is not None
    assert result.status == SubagentStatus.COMPLETED, (
        f"expected COMPLETED, got {result.status} with error={result.error}"
    )
    assert result.result is not None
    assert not result.result.startswith("echo:"), "echo placeholder must be gone"
    assert "real-subagent-output" in result.result


def test_execute_async_writes_stream_events_via_writer(monkeypatch: pytest.MonkeyPatch) -> None:
    """execute_async should emit task_completed via get_stream_writer()."""
    captured_writes: list[dict[str, Any]] = []

    def _writer(payload: dict[str, Any]) -> None:
        captured_writes.append(payload)

    monkeypatch.setattr(executor_module, "get_stream_writer", lambda: _writer)

    fake_graph = _make_fake_graph_with_astream([{"messages": [AIMessage(content="hello")]}])
    monkeypatch.setattr(executor_module, "StateGraph", lambda *a, **kw: _FakeStateGraph(fake_graph))
    monkeypatch.setattr(executor_module, "ChatOpenAI", lambda *a, **kw: MagicMock(name="model"))

    executor = SubagentExecutor(name="general-purpose", prompt="x")
    task_id = executor.execute_async("x", task_id="task-E")
    _wait_for_terminal(task_id)

    event_types = {w.get("type") for w in captured_writes}
    assert "task_completed" in event_types, (
        f"expected task_completed event, saw types={event_types}"
    )
    for w in captured_writes:
        assert w.get("task_id") == task_id, f"event {w} missing task_id"


def test_execute_async_collects_token_usage(monkeypatch: pytest.MonkeyPatch) -> None:
    """Token usage from SubagentTokenCollector flows into SubagentResult.token_usage_records."""

    def _fake_collector_factory(*_args: Any, **_kwargs: Any) -> SubagentTokenCollector:
        c = SubagentTokenCollector(caller="subagent:test")
        c._records.append(
            {
                "source_run_id": "run-1",
                "caller": "subagent:test",
                "model_name": "gpt-test",
                "input_tokens": 3,
                "output_tokens": 4,
                "total_tokens": 7,
            }
        )
        return c

    monkeypatch.setattr(executor_module, "SubagentTokenCollector", _fake_collector_factory)
    monkeypatch.setattr(executor_module, "get_stream_writer", lambda: lambda _p: None)

    fake_graph = _make_fake_graph_with_astream([{"messages": [AIMessage(content="hi")]}])
    monkeypatch.setattr(executor_module, "StateGraph", lambda *a, **kw: _FakeStateGraph(fake_graph))
    monkeypatch.setattr(executor_module, "ChatOpenAI", lambda *a, **kw: MagicMock(name="model"))

    executor = SubagentExecutor(name="general-purpose", prompt="x")
    task_id = executor.execute_async("x", task_id="task-usage")
    result = _wait_for_terminal(task_id)

    assert result is not None
    assert result.status == SubagentStatus.COMPLETED
    assert result.token_usage_records, "token usage must be recorded on result"
    total = sum(r.get("total_tokens", 0) for r in result.token_usage_records)
    assert total >= 7


def test_execute_async_reports_failure_on_graph_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    """If astream raises, status becomes FAILED and the error is captured."""
    monkeypatch.setattr(executor_module, "get_stream_writer", lambda: lambda _p: None)

    fake_graph = MagicMock(name="compiled_subagent_graph")

    async def _boom(_state: dict[str, Any], config: Any = None, **_kwargs: Any):
        raise RuntimeError("simulated-ae-failure")
        yield  # pragma: no cover

    fake_graph.astream = _boom
    monkeypatch.setattr(executor_module, "StateGraph", lambda *a, **kw: _FakeStateGraph(fake_graph))
    monkeypatch.setattr(executor_module, "ChatOpenAI", lambda *a, **kw: MagicMock(name="model"))

    executor = SubagentExecutor(name="general-purpose", prompt="x")
    task_id = executor.execute_async("x", task_id="task-fail")
    result = _wait_for_terminal(task_id)

    assert result is not None
    assert result.status == SubagentStatus.FAILED
    assert "simulated-ae-failure" in (result.error or "")
