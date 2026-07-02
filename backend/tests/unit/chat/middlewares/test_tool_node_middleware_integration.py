"""Integration test: ToolNode invokes the middleware chain.

Verifies that ClarificationMiddleware correctly intercepts tool calls
via ``awrap_tool_call``.  The wiring into ``ToolNode`` is handled by
``create_agent`` internally; these tests drive the middleware's
``awrap_tool_call`` directly.
"""

from __future__ import annotations

from typing import Any

import pytest
from langgraph.graph import END
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.types import Command

from app.core.chat.middlewares.clarification_middleware import ClarificationMiddleware


def _request(
    tool_name: str, tool_call_id: str = "call-1", args: dict | None = None
) -> ToolCallRequest:
    return ToolCallRequest(
        tool_call={
            "name": tool_name,
            "args": args or {},
            "id": tool_call_id,
            "type": "tool_call",
        },
        tool=None,  # type: ignore[arg-type]
        state={"messages": []},
        runtime=None,  # type: ignore[arg-type]
    )


@pytest.mark.asyncio
async def test_clarification_intercepts_and_skips_handler() -> None:
    """ClarificationMiddleware.awrap_tool_call intercepts
    ``ask_clarification`` and returns a ``Command``, skipping the handler."""
    mw = ClarificationMiddleware()

    handler_calls: list[str] = []

    async def handler(req: ToolCallRequest) -> Any:
        handler_calls.append("ran")
        return "should-not-happen"

    req = _request("ask_clarification", args={"question": "需要补充信息"})
    result = await mw.awrap_tool_call(req, handler)
    assert handler_calls == []  # real tool execution skipped
    assert isinstance(result, Command)
    assert result.goto is END
    msgs = result.update.get("messages", [])
    assert any(getattr(m, "content", "").find("需要补充信息") != -1 for m in msgs)

    # A normal tool call → handler IS invoked
    req2 = _request("echo")
    result2 = await mw.awrap_tool_call(req2, handler)
    assert handler_calls == ["ran"]
    assert result2 == "should-not-happen"
