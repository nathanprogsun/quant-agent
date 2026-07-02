"""Tests for the middleware chain validator."""

from __future__ import annotations

import pytest
from langchain.agents.middleware import AgentMiddleware

from app.core.chat.middlewares.validator import MiddlewareChainError, validate_chain


class _A(AgentMiddleware):
    pass


class _B(AgentMiddleware):
    pass


def test_empty_chain_ok() -> None:
    validate_chain([])


def test_distinct_chain_ok() -> None:
    validate_chain([_A(), _B()])


def test_duplicate_class_raises() -> None:
    with pytest.raises(MiddlewareChainError, match="duplicate"):
        validate_chain([_A(), _A()])


def test_dangling_anchor_raises() -> None:
    class _C(AgentMiddleware):
        pass

    class _BadAnchored(AgentMiddleware):
        # _next_anchor set externally
        pass

    _BadAnchored._next_anchor = _C  # type: ignore[attr-defined]
    try:
        with pytest.raises(MiddlewareChainError, match="anchors"):
            validate_chain([_A(), _BadAnchored()])
    finally:
        delattr(_BadAnchored, "_next_anchor")


def test_resolved_anchor_ok() -> None:
    class _BeforeB(AgentMiddleware):
        pass

    _BeforeB._prev_anchor = _B  # type: ignore[attr-defined]
    try:
        validate_chain([_A(), _BeforeB(), _B()])
    finally:
        delattr(_BeforeB, "_prev_anchor")


def test_tool_call_interceptor_without_override_raises() -> None:
    """A middleware that declares _tool_call_interceptor but does not
    override awrap_tool_call must be rejected — ToolNode would bypass it
    silently otherwise."""

    class _StubInterceptor(AgentMiddleware):
        _tool_call_interceptor = True

    try:
        with pytest.raises(MiddlewareChainError, match="_tool_call_interceptor"):
            validate_chain([_A(), _StubInterceptor()])
    finally:
        # leave class attr in place; it is local to this test function
        pass


def test_tool_call_interceptor_with_override_ok() -> None:
    class _RealInterceptor(AgentMiddleware):
        _tool_call_interceptor = True

        async def awrap_tool_call(self, request, handler):  # type: ignore[no-untyped-def]
            return await handler(request)

    validate_chain([_A(), _RealInterceptor()])
