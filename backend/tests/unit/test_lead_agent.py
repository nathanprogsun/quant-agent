"""Unit tests for agent layer — ThreadState, agent_node, middleware chain."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.core.chat.agent.lead_agent import _make_agent_node, _should_use_tools
from app.core.chat.agent.thread_state import ThreadState
from app.core.chat.middlewares.base import AgentMiddleware

# ── ThreadState ──────────────────────────────────────────────


def test_thread_state_accepts_messages() -> None:
    """ThreadState accepts messages field with LangChain types."""
    state: ThreadState = {
        "messages": [HumanMessage(content="hello")],
    }
    assert len(state["messages"]) == 1
    assert state["messages"][0].content == "hello"


def test_thread_state_all_fields_optional() -> None:
    """ThreadState with total=False — empty dict is valid."""
    state: ThreadState = {}
    assert state.get("messages") is None
    assert state.get("title") is None
    assert state.get("code") is None


# ── _should_use_tools ────────────────────────────────────────


def test_should_use_tools_no_messages() -> None:
    """Empty messages → END."""
    state: ThreadState = {"messages": []}
    assert _should_use_tools(state) == "__end__"


def test_should_use_tools_no_tool_calls() -> None:
    """AIMessage without tool_calls → END."""
    state: ThreadState = {
        "messages": [AIMessage(content="hello")],
    }
    assert _should_use_tools(state) == "__end__"


def test_should_use_tools_with_tool_calls() -> None:
    """AIMessage with tool_calls → 'tools'."""
    state: ThreadState = {
        "messages": [
            AIMessage(
                content="",
                tool_calls=[{"name": "search", "args": {"q": "test"}, "id": "1"}],
            ),
        ],
    }
    assert _should_use_tools(state) == "tools"


# ── agent_node middleware chain ───────────────────────────────


class RecordingMiddleware(AgentMiddleware):
    """Middleware that records hook invocations."""

    def __init__(self) -> None:
        self.before_model_calls: list[dict[str, Any]] = []
        self.after_model_calls: list[dict[str, Any]] = []

    async def before_model(self, state: dict[str, Any], config: dict[str, Any]) -> dict[str, Any] | None:
        self.before_model_calls.append(state)
        return None

    async def after_model(self, state: dict[str, Any], config: dict[str, Any]) -> dict[str, Any] | None:
        self.after_model_calls.append(state)
        return None


@pytest.mark.asyncio
async def test_agent_node_calls_middlewares() -> None:
    """agent_node invokes before_model and after_model hooks."""
    mw = RecordingMiddleware()

    mock_model = AsyncMock()
    mock_model.ainvoke = AsyncMock(return_value=AIMessage(content="response"))

    node = _make_agent_node(
        model=mock_model,
        system_prompt="test prompt",
        middlewares=[mw],
    )

    state: ThreadState = {"messages": [HumanMessage(content="hi")]}
    result = await node(state)

    assert len(mw.before_model_calls) == 1
    assert len(mw.after_model_calls) == 1
    assert result["messages"][0].content == "response"


@pytest.mark.asyncio
async def test_agent_node_passes_full_history_to_after_model() -> None:
    """after_model hooks should see prior messages, not only the latest AI reply."""
    mw = RecordingMiddleware()
    mock_model = AsyncMock()
    mock_model.ainvoke = AsyncMock(return_value=AIMessage(content="response"))

    node = _make_agent_node(
        model=mock_model,
        system_prompt="test prompt",
        middlewares=[mw],
    )

    state: ThreadState = {"messages": [HumanMessage(content="hi")]}
    await node(state)

    after_state = mw.after_model_calls[0]
    assert len(after_state["messages"]) == 2
    assert after_state["messages"][0].content == "hi"
    assert after_state["messages"][1].content == "response"


@pytest.mark.asyncio
async def test_agent_node_injects_system_prompt() -> None:
    """agent_node prepends SystemMessage if not present."""
    mock_model = AsyncMock()
    mock_model.ainvoke = AsyncMock(return_value=AIMessage(content="ok"))

    node = _make_agent_node(
        model=mock_model,
        system_prompt="system instructions",
        middlewares=[],
    )

    state: ThreadState = {"messages": [HumanMessage(content="hi")]}
    await node(state)

    call_args = mock_model.ainvoke.call_args[0][0]
    assert isinstance(call_args[0], SystemMessage)
    assert call_args[0].content == "system instructions"


@pytest.mark.asyncio
async def test_agent_node_refreshes_stale_system_prompt() -> None:
    """Stale checkpoint SystemMessage is replaced with the current system prompt."""
    mock_model = AsyncMock()
    mock_model.ainvoke = AsyncMock(return_value=AIMessage(content="ok"))

    node = _make_agent_node(
        model=mock_model,
        system_prompt="system instructions",
        middlewares=[],
    )

    state: ThreadState = {
        "messages": [
            SystemMessage(content="custom prompt"),
            HumanMessage(content="hi"),
        ],
    }
    await node(state)

    call_args = mock_model.ainvoke.call_args[0][0]
    assert call_args[0].content == "system instructions"
    assert len(call_args) == 2


@pytest.mark.asyncio
async def test_agent_node_passes_system_prompt_to_before_model() -> None:
    """before_model hooks receive the injected system prompt in state."""
    mw = RecordingMiddleware()
    mock_model = AsyncMock()
    mock_model.ainvoke = AsyncMock(return_value=AIMessage(content="response"))

    node = _make_agent_node(
        model=mock_model,
        system_prompt="system instructions",
        middlewares=[mw],
    )

    state: ThreadState = {"messages": [HumanMessage(content="hi")]}
    await node(state)

    before_state = mw.before_model_calls[0]
    assert isinstance(before_state["messages"][0], SystemMessage)
    assert before_state["messages"][0].content == "system instructions"
