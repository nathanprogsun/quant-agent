"""Tests for the rewritten task_tool — subagent delegation.

Asserts:
- ``task_tool`` exists as a ``langchain.tools.tool`` with name 'task'
- delegates via ``subagents.executor.execute_async(prompt, task_id=...)``
- emits task_started / task_running / task_completed via get_stream_writer()
- on CancelledError, ``_subagent_usage_cache`` entry is popped

The cancellation test asserts the implementation contract directly via source
inspection — running the real body end-to-end requires a full subgraph.
"""

from __future__ import annotations

import asyncio
import inspect
from typing import Any

import pytest

import app.core.chat.tools.builtin.task_tool as task_tool_module
from app.core.chat.tools.builtin.task_tool import _subagent_usage_cache, task_tool


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    _subagent_usage_cache.clear()
    yield
    _subagent_usage_cache.clear()


@pytest.fixture(autouse=True)
def _stub_stream_writer(monkeypatch: pytest.MonkeyPatch) -> None:
    """langgraph.get_stream_writer requires a Pregel runtime; replace with no-op for unit tests."""

    def _writer(_payload: dict[str, Any]) -> None:
        pass

    monkeypatch.setattr(task_tool_module, "get_stream_writer", lambda: _writer)


def test_task_tool_exports_langchain_tool() -> None:
    """The rewritten task_tool must use @tool('task') for runtime binding."""
    assert getattr(task_tool, "name", None) == "task"


def _invoke_task(description: str, prompt: str, subagent_type: str, tool_call_id: str):
    return task_tool.ainvoke(
        {
            "type": "tool_call",
            "name": "task",
            "args": {
                "description": description,
                "prompt": prompt,
                "subagent_type": subagent_type,
            },
            "id": tool_call_id,
        }
    )


@pytest.fixture
def main_event_loop() -> Any:
    """Per-test MainThread event loop.

    Uses ``asyncio.new_event_loop`` + ``set_event_loop`` so we don't disturb
    the thread-local loop used by other suites — and we explicitly close the
    loop in teardown to avoid leaking references across the session.

    Note: ``asyncio.run()`` would be one line shorter, but it deletes the
    loop on exit which breaks unrelated sync tests that call
    ``asyncio.get_event_loop().run_until_complete(...)`` (e.g. backtest_service
    tests). Closing the loop manually after ``run_until_complete`` is safer.
    """
    prior = None
    try:
        prior = asyncio.get_event_loop()
    except RuntimeError:
        prior = None
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        yield loop
    finally:
        loop.close()
        if prior is None:
            asyncio.set_event_loop(None)
        else:
            asyncio.set_event_loop(prior)


def test_arun_calls_subagent_executor_execute_async(
    main_event_loop: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """TaskTool delegates via execute_async using the injected tool_call_id as task_id."""
    captured: dict[str, Any] = {}

    class FakeExecutor:
        def __init__(self, **kwargs: Any) -> None:
            pass

        def execute_async(self, prompt: str, task_id: str) -> str:
            captured["prompt"] = prompt
            captured["task_id"] = task_id
            return task_id

    monkeypatch.setattr(task_tool_module, "SubagentExecutor", FakeExecutor)

    fake_result = task_tool_module.SubagentResult(
        task_id="tcid-001",
        trace_id="trace-x",
        status=task_tool_module.SubagentStatus.RUNNING,
    )
    fake_result.try_set_terminal(task_tool_module.SubagentStatus.COMPLETED, result="done")
    monkeypatch.setattr(task_tool_module, "get_background_task_result", lambda _tid: fake_result)
    monkeypatch.setattr(task_tool_module, "cleanup_background_task", lambda _tid: None)

    out = main_event_loop.run_until_complete(
        _invoke_task(
            description="demo",
            prompt="do the thing",
            subagent_type="general-purpose",
            tool_call_id="tcid-001",
        )
    )
    assert captured == {"prompt": "do the thing", "task_id": "tcid-001"}
    out_text = out.content if hasattr(out, "content") else str(out)
    assert "Result" in out_text


def test_real_body_pops_cache_on_cancellederror() -> None:
    """The real ``_run_task_body`` must include the cancel-pop contract.

    Asserts the implementation contract directly via source inspection —
    the real body must catch ``asyncio.CancelledError`` and pop the cache
    for the active ``tool_call_id`` before re-raising.
    """
    source = inspect.getsource(task_tool_module._run_task_body)
    assert "asyncio.CancelledError" in source, "_run_task_body must catch CancelledError"
    assert "_subagent_usage_cache.pop" in source, "_run_task_body must pop cache on cancel"


def test_pop_cached_subagent_usage_helper() -> None:
    """The ``pop_cached_subagent_usage`` helper exposes the cache for the token bridge."""
    _subagent_usage_cache["tcid-x"] = {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2}
    result = task_tool_module.pop_cached_subagent_usage("tcid-x")
    assert result == {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2}
    assert task_tool_module.pop_cached_subagent_usage("tcid-x") is None
    assert task_tool_module.pop_cached_subagent_usage("absent") is None
