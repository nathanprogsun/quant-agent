"""Tests for SystemMessageCoalescingMiddleware.

Verifies that multiple SystemMessages in the request are merged into one
at the front of the message list before reaching the model — required for
strict backends (vLLM, SGLang, Qwen, Anthropic) that reject non-leading
SystemMessages. Persistent state is left untouched.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from langchain.agents.middleware import ModelRequest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.core.chat.middlewares.system_message_coalescing_middleware import (
    SystemMessageCoalescingMiddleware,
)


async def _capture(seen: dict[str, Any]):
    async def handler(request: ModelRequest) -> str:
        seen["messages"] = list(request.messages)
        return "ok"

    return handler


@pytest.mark.asyncio
async def test_single_system_message_passthrough() -> None:
    mw = SystemMessageCoalescingMiddleware()
    seen: dict[str, Any] = {}
    request = ModelRequest(
        model=MagicMock(),
        messages=[
            SystemMessage(content="sys A"),
            HumanMessage(content="hi", id="u1"),
        ],
    )
    await mw.awrap_model_call(request, await _capture(seen))
    sys_count = sum(1 for m in seen["messages"] if isinstance(m, SystemMessage))
    assert sys_count == 1


@pytest.mark.asyncio
async def test_multiple_system_messages_merged() -> None:
    mw = SystemMessageCoalescingMiddleware()
    seen: dict[str, Any] = {}
    request = ModelRequest(
        model=MagicMock(),
        messages=[
            SystemMessage(content="sys A", id="sa"),
            SystemMessage(content="sys B", id="sb"),
            SystemMessage(content="sys C", id="sc"),
            HumanMessage(content="hi", id="u1"),
        ],
    )
    await mw.awrap_model_call(request, await _capture(seen))
    sys_msgs = [m for m in seen["messages"] if isinstance(m, SystemMessage)]
    assert len(sys_msgs) == 1
    merged = sys_msgs[0].content
    assert "sys A" in merged
    assert "sys B" in merged
    assert "sys C" in merged


@pytest.mark.asyncio
async def test_no_system_message_unchanged() -> None:
    mw = SystemMessageCoalescingMiddleware()
    seen: dict[str, Any] = {}
    request = ModelRequest(model=MagicMock(), messages=[HumanMessage(content="hi", id="u1")])
    await mw.awrap_model_call(request, await _capture(seen))
    assert len(seen["messages"]) == 1


@pytest.mark.asyncio
async def test_merged_message_positioned_first() -> None:
    mw = SystemMessageCoalescingMiddleware()
    seen: dict[str, Any] = {}
    request = ModelRequest(
        model=MagicMock(),
        messages=[
            HumanMessage(content="hi", id="u1"),
            SystemMessage(content="sys A", id="sa"),
            SystemMessage(content="sys B", id="sb"),
        ],
    )
    await mw.awrap_model_call(request, await _capture(seen))
    assert isinstance(seen["messages"][0], SystemMessage)
    non_sys = [m for m in seen["messages"][1:] if not isinstance(m, SystemMessage)]
    assert len(non_sys) == 1


@pytest.mark.asyncio
async def test_non_system_messages_preserved_in_order() -> None:
    mw = SystemMessageCoalescingMiddleware()
    seen: dict[str, Any] = {}
    request = ModelRequest(
        model=MagicMock(),
        messages=[
            SystemMessage(content="sys A"),
            HumanMessage(content="first", id="u1"),
            AIMessage(content="assistant"),
            SystemMessage(content="sys B"),
            HumanMessage(content="second", id="u2"),
        ],
    )
    await mw.awrap_model_call(request, await _capture(seen))
    msgs = seen["messages"]
    # First must be SystemMessage
    assert isinstance(msgs[0], SystemMessage)
    # Subsequent order must be preserved
    non_sys = [m for m in msgs[1:] if not isinstance(m, SystemMessage)]
    assert len(non_sys) == 3
    assert isinstance(non_sys[0], HumanMessage)
    assert non_sys[0].content == "first"
    assert isinstance(non_sys[1], AIMessage)
    assert isinstance(non_sys[2], HumanMessage)
    assert non_sys[2].content == "second"


@pytest.mark.asyncio
async def test_separator_join_strings() -> None:
    mw = SystemMessageCoalescingMiddleware(separator="\n---\n")
    seen: dict[str, Any] = {}
    request = ModelRequest(
        model=MagicMock(), messages=[SystemMessage(content="A"), SystemMessage(content="B")]
    )
    await mw.awrap_model_call(request, await _capture(seen))
    assert "A\n---\nB" in seen["messages"][0].content


@pytest.mark.asyncio
async def test_disabled_is_noop() -> None:
    mw = SystemMessageCoalescingMiddleware(enabled=False)
    seen: dict[str, Any] = {}
    request = ModelRequest(
        model=MagicMock(), messages=[SystemMessage(content="A"), SystemMessage(content="B")]
    )
    await mw.awrap_model_call(request, await _capture(seen))
    sys_count = sum(1 for m in seen["messages"] if isinstance(m, SystemMessage))
    assert sys_count == 2
