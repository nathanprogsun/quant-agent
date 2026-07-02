"""Tests for AgentMiddleware wrap_* hook surface.

The ABC must expose wrap_model_call/awrap_model_call (model interceptors)
and wrap_tool_call/awrap_tool_call (tool interceptors). All four default
to no-ops that delegate to the wrapped handler. Subclasses may override
to intercept model or tool calls.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest
from langchain.agents.middleware import AgentMiddleware


class _IdentityMW(AgentMiddleware):
    """Minimal subclass that does not override any hook."""


@pytest.mark.asyncio
async def test_default_awrap_model_call_not_implemented() -> None:
    mw = _IdentityMW()
    with pytest.raises(NotImplementedError):
        await mw.awrap_model_call(request=None, handler=AsyncMock())


@pytest.mark.asyncio
async def test_awrap_model_call_can_short_circuit() -> None:
    class ShortCircuitMW(AgentMiddleware):
        async def awrap_model_call(self, request: Any, handler: Any) -> Any:
            return "short-circuited"

    mw = ShortCircuitMW()
    handler = AsyncMock(return_value="original")
    result = await mw.awrap_model_call(request=None, handler=handler)
    assert result == "short-circuited"
    handler.assert_not_awaited()


def test_wrap_model_call_sync_not_implemented() -> None:
    mw = _IdentityMW()
    with pytest.raises(NotImplementedError):
        mw.wrap_model_call(request=None, handler=lambda r: r)


@pytest.mark.asyncio
async def test_awrap_model_call_subclass_override() -> None:
    class TransformMW(AgentMiddleware):
        async def awrap_model_call(self, request: Any, handler: Any) -> Any:
            out = await handler(request)
            return f"<wrapped>{out}</wrapped>"

    mw = TransformMW()

    async def handler(request: Any) -> Any:
        return "body"

    result = await mw.awrap_model_call(request=None, handler=handler)
    assert result == "<wrapped>body</wrapped>"


@pytest.mark.asyncio
async def test_default_awrap_tool_call_not_implemented() -> None:
    mw = _IdentityMW()
    with pytest.raises(NotImplementedError):
        await mw.awrap_tool_call(request=None, handler=AsyncMock())


def test_wrap_tool_call_sync_not_implemented() -> None:
    mw = _IdentityMW()
    with pytest.raises(NotImplementedError):
        mw.wrap_tool_call(request=None, handler=lambda r: r)
