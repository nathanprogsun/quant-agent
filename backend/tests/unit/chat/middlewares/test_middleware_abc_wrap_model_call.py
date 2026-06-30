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

from app.core.chat.middlewares.base import AgentMiddleware


class _IdentityMW(AgentMiddleware):
    """Minimal subclass that does not override any hook."""


@pytest.mark.asyncio
async def test_default_awrap_model_call_invokes_handler_unchanged() -> None:
    mw = _IdentityMW()
    seen: dict[str, Any] = {}

    async def handler(request: Any) -> Any:
        seen["called"] = True
        return "ok"

    result = await mw.awrap_model_call(request=None, handler=handler)
    assert result == "ok"
    assert seen["called"] is True


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


def test_wrap_model_call_sync_default_exists_and_is_noop() -> None:
    mw = _IdentityMW()
    called = {"v": False}

    def handler(request: Any) -> Any:
        called["v"] = True
        return "sync-ok"

    # Sync hook must exist and delegate by default
    result = mw.wrap_model_call(request=None, handler=handler)
    assert result == "sync-ok"
    assert called["v"] is True


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
async def test_default_awrap_tool_call_invokes_handler_unchanged() -> None:
    mw = _IdentityMW()
    seen: dict[str, Any] = {}

    async def handler(request: Any) -> Any:
        seen["called"] = True
        return "tool-ok"

    result = await mw.awrap_tool_call(request=None, handler=handler)
    assert result == "tool-ok"
    assert seen["called"] is True


def test_wrap_tool_call_sync_default_exists_and_is_noop() -> None:
    mw = _IdentityMW()
    called = {"v": False}

    def handler(request: Any) -> Any:
        called["v"] = True
        return "sync-tool-ok"

    result = mw.wrap_tool_call(request=None, handler=handler)
    assert result == "sync-tool-ok"
    assert called["v"] is True
