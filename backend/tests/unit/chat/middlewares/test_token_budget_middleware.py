"""Tests for TokenBudgetMiddleware.

Verifies per-run token budget enforcement: warning injection at threshold,
hard-stop AIMessage override at hard limit, deferred warning pattern
(after_model queues, wrap_model_call drains), and reset semantics.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from langchain.agents.middleware import ModelRequest
from langchain_core.messages import AIMessage, HumanMessage, UsageMetadata

from app.core.chat.middlewares.token_budget_middleware import (
    TokenBudgetConfig,
    TokenBudgetMiddleware,
)


def _request() -> ModelRequest:
    return ModelRequest(model=MagicMock(), messages=[HumanMessage(content="hi", id="u1")])


def _usage(prompt: int, completion: int) -> UsageMetadata:
    return UsageMetadata(
        input_tokens=prompt,
        output_tokens=completion,
        total_tokens=prompt + completion,
    )


@pytest.mark.asyncio
async def test_no_action_under_warn_threshold() -> None:
    mw = TokenBudgetMiddleware(config=TokenBudgetConfig(warn_threshold=1000, hard_limit=5000))
    state = {
        "messages": [
            HumanMessage(content="hi", id="u1"),
            AIMessage(content="ok", usage_metadata=_usage(100, 50)),
        ]
    }
    # after_model: should not queue a warning
    out = await mw.aafter_model(state, runtime=None)  # type: ignore[arg-type]
    assert out is None


@pytest.mark.asyncio
async def test_warn_threshold_queues_deferred_warning() -> None:
    mw = TokenBudgetMiddleware(config=TokenBudgetConfig(warn_threshold=100, hard_limit=1000))
    state = {
        "messages": [
            HumanMessage(content="hi", id="u1"),
            AIMessage(content="ok", usage_metadata=_usage(200, 50)),
        ]
    }
    await mw.aafter_model(state, runtime=None)  # type: ignore[arg-type]

    seen: dict[str, Any] = {}
    request = _request()

    async def handler(req: ModelRequest) -> str:
        seen["messages"] = list(req.messages)
        return "ok"

    result = await mw.awrap_model_call(request, handler)
    assert result == "ok"
    injected = [m for m in seen["messages"] if m.id != "u1"]
    assert len(injected) >= 1
    assert any(
        "token budget" in m.content.lower() or "token" in m.content.lower() for m in injected
    )


@pytest.mark.asyncio
async def test_hard_limit_replaces_response_with_hard_stop() -> None:
    mw = TokenBudgetMiddleware(config=TokenBudgetConfig(warn_threshold=100, hard_limit=500))

    state = {
        "messages": [
            HumanMessage(content="hi", id="u1"),
            AIMessage(content="partial answer", usage_metadata=_usage(600, 100)),
        ]
    }
    out = await mw.aafter_model(state, runtime=None)  # type: ignore[arg-type]
    # Hard stop should mutate the last AIMessage via state_update
    assert out is not None
    new_messages = out.get("messages", [])
    assert new_messages
    last = new_messages[-1]
    assert isinstance(last, AIMessage)
    assert not last.tool_calls  # tool_calls cleared
    assert "token" in last.content.lower() or "budget" in last.content.lower()


@pytest.mark.asyncio
async def test_pending_warnings_drained_on_next_call() -> None:
    mw = TokenBudgetMiddleware(config=TokenBudgetConfig(warn_threshold=100, hard_limit=1000))
    state = {
        "messages": [
            HumanMessage(content="hi", id="u1"),
            AIMessage(content="ok", usage_metadata=_usage(200, 50)),
        ]
    }
    await mw.aafter_model(state, runtime=None)  # type: ignore[arg-type]
    # First drain
    seen1: dict[str, Any] = {}
    req1 = _request()

    async def handler1(req: ModelRequest) -> str:
        seen1["messages"] = list(req.messages)
        return "ok"

    await mw.awrap_model_call(req1, handler1)
    assert len(seen1["messages"]) >= 2  # original + warning

    # Second call should NOT have the warning again
    seen2: dict[str, Any] = {}
    req2 = _request()

    async def handler2(req: ModelRequest) -> str:
        seen2["messages"] = list(req.messages)
        return "ok"

    await mw.awrap_model_call(req2, handler2)
    assert len(seen2["messages"]) == 1  # only original


@pytest.mark.asyncio
async def test_disabled_middleware_is_noop() -> None:
    mw = TokenBudgetMiddleware(
        config=TokenBudgetConfig(enabled=False, warn_threshold=100, hard_limit=500)
    )
    state = {
        "messages": [
            HumanMessage(content="hi", id="u1"),
            AIMessage(content="ok", usage_metadata=_usage(1000, 500)),
        ]
    }
    out = await mw.aafter_model(state, runtime=None)  # type: ignore[arg-type]
    assert out is None


@pytest.mark.asyncio
async def test_reset_clears_state() -> None:
    mw = TokenBudgetMiddleware(config=TokenBudgetConfig(warn_threshold=100, hard_limit=500))
    state = {
        "messages": [
            HumanMessage(content="hi", id="u1"),
            AIMessage(content="ok", usage_metadata=_usage(200, 50)),
        ]
    }
    await mw.aafter_model(state, runtime=None)  # type: ignore[arg-type]
    mw.reset()
    seen: dict[str, Any] = {}
    request = _request()

    async def handler(req: ModelRequest) -> str:
        seen["messages"] = list(req.messages)
        return "ok"

    await mw.awrap_model_call(request, handler)
    assert len(seen["messages"]) == 1


def test_default_config_values() -> None:
    cfg = TokenBudgetConfig()
    assert cfg.enabled is True
    assert cfg.warn_threshold > 0
    assert cfg.hard_limit > cfg.warn_threshold
