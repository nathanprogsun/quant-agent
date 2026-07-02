"""Tests for LLMErrorHandlingMiddleware.

Verifies:
- Error classification (quota/auth/transient/busy)
- Exponential-backoff retry on transient failures
- Circuit breaker state machine (closed → open → half_open → closed)
- Fallback AIMessage returned when circuit is open or retries exhausted
- GraphBubbleUp propagation
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain.agents.middleware import ModelRequest
from langchain_core.messages import AIMessage
from langgraph.errors import GraphBubbleUp

from app.core.chat.middlewares.llm_error_handling_middleware import (
    CircuitBreaker,
    CircuitState,
    ErrorCategory,
    LLMErrorConfig,
    LLMErrorHandlingMiddleware,
    classify_error,
)


def _request() -> ModelRequest:
    return ModelRequest(model=MagicMock(), messages=[])


# ───────────────────── classify_error ─────────────────────


def test_classify_quota_error() -> None:
    err = RuntimeError("429 quota exceeded")
    assert classify_error(err) == ErrorCategory.QUOTA


def test_classify_auth_error() -> None:
    err = RuntimeError("401 unauthorized: invalid api key")
    assert classify_error(err) == ErrorCategory.AUTH


def test_classify_timeout_error() -> None:
    err = RuntimeError("ReadTimeout: connection timed out after 30s")
    assert classify_error(err) == ErrorCategory.TIMEOUT


def test_classify_busy_error() -> None:
    err = RuntimeError("503 service unavailable, server overloaded")
    assert classify_error(err) == ErrorCategory.BUSY


def test_classify_unknown_defaults_to_transient() -> None:
    err = RuntimeError("something weird happened")
    assert classify_error(err) == ErrorCategory.TRANSIENT


# ───────────────────── CircuitBreaker ─────────────────────


def test_circuit_breaker_starts_closed() -> None:
    cb = CircuitBreaker(failure_threshold=3, window_seconds=60.0, reset_timeout=30.0)
    assert cb.state == CircuitState.CLOSED
    assert cb.allow_request() is True


def test_circuit_breaker_opens_after_threshold() -> None:
    cb = CircuitBreaker(failure_threshold=3, window_seconds=60.0, reset_timeout=30.0)
    for _ in range(3):
        cb.record_failure()
    assert cb.state == CircuitState.OPEN
    assert cb.allow_request() is False


def test_circuit_breaker_half_open_after_reset_timeout() -> None:
    cb = CircuitBreaker(failure_threshold=2, window_seconds=60.0, reset_timeout=0.0)
    cb.record_failure()
    cb.record_failure()
    assert cb.state == CircuitState.OPEN
    assert cb.allow_request() is True  # reset_timeout=0 immediately half-opens
    assert cb.state == CircuitState.HALF_OPEN


def test_circuit_breaker_closes_after_success_in_half_open() -> None:
    cb = CircuitBreaker(failure_threshold=2, window_seconds=60.0, reset_timeout=0.0)
    cb.record_failure()
    cb.record_failure()
    cb.allow_request()  # → half_open
    cb.record_success()
    assert cb.state == CircuitState.CLOSED


def test_circuit_breaker_reopens_on_failure_in_half_open() -> None:
    cb = CircuitBreaker(failure_threshold=2, window_seconds=60.0, reset_timeout=0.0)
    cb.record_failure()
    cb.record_failure()
    cb.allow_request()  # → half_open
    cb.record_failure()
    assert cb.state == CircuitState.OPEN


# ───────────────────── Middleware retry + fallback ─────────────────────


@pytest.mark.asyncio
async def test_successful_call_passes_through() -> None:
    mw = LLMErrorHandlingMiddleware(config=LLMErrorConfig(max_retries=2, base_delay=0.0))
    handler = AsyncMock(return_value=AIMessage(content="ok"))
    result = await mw.awrap_model_call(_request(), handler)
    assert isinstance(result, AIMessage)
    assert result.content == "ok"
    handler.assert_awaited_once()


@pytest.mark.asyncio
async def test_retries_transient_then_succeeds() -> None:
    mw = LLMErrorHandlingMiddleware(config=LLMErrorConfig(max_retries=3, base_delay=0.0))
    call_count = {"n": 0}

    async def handler(req: ModelRequest) -> Any:
        call_count["n"] += 1
        if call_count["n"] < 3:
            raise RuntimeError("connection timeout")
        return AIMessage(content="recovered")

    result = await mw.awrap_model_call(_request(), handler)
    assert isinstance(result, AIMessage)
    assert result.content == "recovered"
    assert call_count["n"] == 3


@pytest.mark.asyncio
async def test_auth_error_does_not_retry() -> None:
    mw = LLMErrorHandlingMiddleware(config=LLMErrorConfig(max_retries=5, base_delay=0.0))
    handler = AsyncMock(side_effect=RuntimeError("401 unauthorized"))

    result = await mw.awrap_model_call(_request(), handler)
    assert isinstance(result, AIMessage)
    assert handler.await_count == 1  # no retry on auth
    # Fallback message should mention authentication
    assert (
        "身份验证" in result.content or "鉴权" in result.content or "auth" in result.content.lower()
    )


@pytest.mark.asyncio
async def test_quota_error_does_not_retry() -> None:
    mw = LLMErrorHandlingMiddleware(config=LLMErrorConfig(max_retries=5, base_delay=0.0))
    handler = AsyncMock(side_effect=RuntimeError("429 quota exceeded"))

    result = await mw.awrap_model_call(_request(), handler)
    assert isinstance(result, AIMessage)
    assert handler.await_count == 1
    assert "配额" in result.content or "quota" in result.content.lower()


@pytest.mark.asyncio
async def test_fallback_after_retries_exhausted() -> None:
    mw = LLMErrorHandlingMiddleware(
        config=LLMErrorConfig(max_retries=2, base_delay=0.0, exponential_base=1.0)
    )
    handler = AsyncMock(side_effect=RuntimeError("connection timeout"))

    result = await mw.awrap_model_call(_request(), handler)
    assert isinstance(result, AIMessage)
    assert handler.await_count == 3  # 1 initial + 2 retries
    assert "重试" in result.content or "繁忙" in result.content or "稍后再试" in result.content


@pytest.mark.asyncio
async def test_circuit_open_short_circuits_to_fallback() -> None:
    mw = LLMErrorHandlingMiddleware(
        config=LLMErrorConfig(
            max_retries=2,
            base_delay=0.0,
            circuit_failure_threshold=2,
            circuit_window_seconds=60.0,
            circuit_reset_timeout=999.0,
        )
    )

    # First two calls open the circuit
    for _ in range(2):
        handler = AsyncMock(side_effect=RuntimeError("connection timeout"))
        await mw.awrap_model_call(_request(), handler)

    # Third call should be short-circuited
    handler3 = AsyncMock(return_value=AIMessage(content="should not reach"))
    result = await mw.awrap_model_call(_request(), handler3)
    assert isinstance(result, AIMessage)
    assert handler3.await_count == 0
    assert (
        result.metadata.get("circuit_open") is True
        or "熔断" in result.content
        or "稍后" in result.content
    )


@pytest.mark.asyncio
async def test_graph_bubble_up_propagates() -> None:
    mw = LLMErrorHandlingMiddleware(config=LLMErrorConfig(max_retries=3, base_delay=0.0))
    handler = AsyncMock(side_effect=GraphBubbleUp("control flow"))

    with pytest.raises(GraphBubbleUp):
        await mw.awrap_model_call(_request(), handler)


@pytest.mark.asyncio
async def test_disabled_middleware_is_noop() -> None:
    mw = LLMErrorHandlingMiddleware(config=LLMErrorConfig(enabled=False))
    handler = AsyncMock(side_effect=RuntimeError("connection timeout"))

    with pytest.raises(RuntimeError):
        await mw.awrap_model_call(_request(), handler)


@pytest.mark.asyncio
async def test_reset_clears_state() -> None:
    mw = LLMErrorHandlingMiddleware(config=LLMErrorConfig(max_retries=2, base_delay=0.0))
    handler = AsyncMock(side_effect=RuntimeError("connection timeout"))
    await mw.awrap_model_call(_request(), handler)
    mw.reset()
    assert mw.circuit_breaker.state == CircuitState.CLOSED
