"""Tests for the ``checkpointer=False`` enforcement on subagent graphs.

quant-agent does NOT use ``langchain.agents.create_agent`` (the ``langchain``
package is not installed). Subagents are built with a manual
``StateGraph(...).compile(checkpointer=False)`` mirroring lead_agent.py.

The guard targets ``StateGraph.compile`` directly. If a caller passes a
parent checkpointer the executor raises ``NotImplementedError`` so the
regression is loud.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from app.core.chat.subagents.executor import compile_subagent_graph


class _FakeStateGraph:
    """Captures compile() kwargs without spinning up a real graph."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.compile_calls: list[dict[str, Any]] = []

    def add_node(self, *args: Any, **kwargs: Any) -> None:
        return None

    def set_entry_point(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def add_edge(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def add_conditional_edges(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def compile(self, **kwargs: Any) -> Any:
        self.compile_calls.append(kwargs)
        return MagicMock(name="compiled_graph")


def test_compile_subagent_graph_passes_checkpointer_false(monkeypatch: pytest.MonkeyPatch) -> None:
    graph = _FakeStateGraph()
    monkeypatch.setattr(
        "app.core.chat.subagents.executor.StateGraph",
        lambda *a, **kw: graph,
    )
    monkeypatch.setattr(
        "app.core.chat.subagents.executor.ChatOpenAI",
        lambda *a, **kw: MagicMock(name="model"),
    )

    out = compile_subagent_graph(model_name="m")
    assert graph.compile_calls, "compile() must run"
    kwargs = graph.compile_calls[0]
    assert kwargs.get("checkpointer") is False
    assert out is not None, "compile() must return a graph"


def test_compile_subagent_rejects_parent_checkpointer(monkeypatch: pytest.MonkeyPatch) -> None:
    graph = _FakeStateGraph()
    monkeypatch.setattr(
        "app.core.chat.subagents.executor.StateGraph",
        lambda *a, **kw: graph,
    )

    with pytest.raises(NotImplementedError):
        compile_subagent_graph(model_name="m", checkpointer=object())
