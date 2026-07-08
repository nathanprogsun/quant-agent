"""LLM error handling middleware — retry, circuit breaker, fallback.

Operates at the outermost layer of the ``awrap_model_call`` chain so it
sees every model invocation (and its exceptions) regardless of which
downstream middleware short-circuits or transforms the request.

Defense layers:

1. **Error classification** — errors are bucketed into
   ``quota`` / ``auth`` / ``timeout`` / ``busy`` / ``transient`` /
   ``control_flow``. Non-retryable buckets (auth, quota) skip retry.
2. **Exponential-backoff retry** — only ``timeout`` / ``busy`` /
   ``transient`` errors retry up to ``max_retries`` times.
3. **Circuit breaker** — after ``circuit_failure_threshold`` failures
   within ``circuit_window_seconds``, the breaker opens and short-circuits
   to a fallback ``AIMessage`` for ``circuit_reset_timeout`` seconds,
   then half-opens to probe recovery.
4. **GraphBubbleUp propagation** — langgraph control-flow signals always
   re-raise so interrupt / pause / resume semantics are preserved.

Mirrors legacy ``llm_error_handling_middleware.py`` adapted to
quant-agent's ``ModelRequest`` carrier.
"""

from __future__ import annotations

import asyncio
import enum
import logging
import re
import threading
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, override

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware, ModelRequest
from langchain.agents.middleware.types import ModelCallResult, ModelResponse
from langchain_core.messages import AIMessage
from langgraph.errors import GraphBubbleUp

logger = logging.getLogger(__name__)


class ErrorCategory(enum.Enum):
    QUOTA = "quota"
    AUTH = "auth"
    TIMEOUT = "timeout"
    BUSY = "busy"
    TRANSIENT = "transient"
    CONTROL_FLOW = "control_flow"


class CircuitState(enum.Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


_ERROR_PATTERNS: dict[ErrorCategory, tuple[str, ...]] = {
    ErrorCategory.QUOTA: (r"429", r"quota", r"rate.?limit", r"insufficient.*quota"),
    ErrorCategory.AUTH: (
        r"401",
        r"403",
        r"unauthorized",
        r"forbidden",
        r"invalid.*api.?key",
        r"auth.*fail",
    ),
    ErrorCategory.TIMEOUT: (r"timeout", r"timed.?out", r"ReadTimeout", r"deadline.?exceeded"),
    ErrorCategory.BUSY: (r"503", r"504", r"overloaded", r"service.*unavailable", r"server.*busy"),
}


def classify_error(err: BaseException) -> ErrorCategory:
    """Bucket an exception into an ErrorCategory.

    ``GraphBubbleUp`` and ``KeyboardInterrupt`` map to ``CONTROL_FLOW`` so
    callers can preserve langgraph interrupt / pause / resume semantics.
    """
    if isinstance(err, (GraphBubbleUp, KeyboardInterrupt, asyncio.CancelledError)):
        return ErrorCategory.CONTROL_FLOW
    msg = f"{type(err).__name__}: {err}".lower()
    for cat, patterns in _ERROR_PATTERNS.items():
        for pat in patterns:
            if re.search(pat, msg, re.IGNORECASE):
                return cat
    return ErrorCategory.TRANSIENT


_RETRYABLE_CATEGORIES: frozenset[ErrorCategory] = frozenset(
    {ErrorCategory.TIMEOUT, ErrorCategory.BUSY, ErrorCategory.TRANSIENT}
)


@dataclass
class LLMErrorConfig:
    """Configuration for LLMErrorHandlingMiddleware."""

    enabled: bool = True
    max_retries: int = 3
    base_delay: float = 0.5
    max_delay: float = 30.0
    exponential_base: float = 2.0
    circuit_failure_threshold: int = 5
    circuit_window_seconds: float = 60.0
    circuit_reset_timeout: float = 30.0
    fallback_responses: dict[ErrorCategory, str] = field(
        default_factory=lambda: {
            ErrorCategory.AUTH: "身份验证失败（401/403）。请检查 API Key 后再试。",
            ErrorCategory.QUOTA: "API 配额已用尽（429）。请稍后再试或提升配额。",
            ErrorCategory.TIMEOUT: "模型响应超时，已重试多次。请稍后再试。",
            ErrorCategory.BUSY: "上游模型服务繁忙（503/504），已重试。请稍后再试。",
            ErrorCategory.TRANSIENT: "模型调用暂时失败，已重试。请稍后再试。",
        }
    )


class CircuitBreaker:
    """Windowed failure-count circuit breaker.

    State machine:
    - ``CLOSED`` — requests pass through; failures are counted.
    - ``OPEN`` — requests short-circuit until ``reset_timeout`` elapses.
    - ``HALF_OPEN`` — a single probe is allowed; success → ``CLOSED``,
      failure → ``OPEN``.
    """

    def __init__(
        self,
        *,
        failure_threshold: int = 5,
        window_seconds: float = 60.0,
        reset_timeout: float = 30.0,
    ) -> None:
        self._failure_threshold = max(1, failure_threshold)
        self._window_seconds = window_seconds
        self._reset_timeout = reset_timeout
        self._lock = threading.Lock()
        self._state: CircuitState = CircuitState.CLOSED
        self._failures: list[float] = []  # timestamps within window
        self._opened_at: float = 0.0

    @property
    def state(self) -> CircuitState:
        with self._lock:
            return self._state

    def allow_request(self) -> bool:
        """Return True if a request may proceed; possibly transition state."""
        with self._lock:
            now = time.monotonic()
            if self._state == CircuitState.OPEN:
                if now - self._opened_at >= self._reset_timeout:
                    self._state = CircuitState.HALF_OPEN
                    return True
                return False
            return True

    def record_success(self) -> None:
        with self._lock:
            self._failures.clear()
            self._state = CircuitState.CLOSED
            self._opened_at = 0.0

    def record_failure(self) -> None:
        with self._lock:
            now = time.monotonic()
            self._failures = [t for t in self._failures if now - t <= self._window_seconds]
            self._failures.append(now)
            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.OPEN
                self._opened_at = now
                return
            if len(self._failures) >= self._failure_threshold:
                self._state = CircuitState.OPEN
                self._opened_at = now


class LLMErrorHandlingMiddleware(AgentMiddleware[AgentState]):
    """Wrap model invocations with retry, circuit breaker, and fallback."""

    def __init__(self, config: LLMErrorConfig | None = None) -> None:
        super().__init__()
        self._config = config or LLMErrorConfig()
        self._circuit = CircuitBreaker(
            failure_threshold=self._config.circuit_failure_threshold,
            window_seconds=self._config.circuit_window_seconds,
            reset_timeout=self._config.circuit_reset_timeout,
        )

    @property
    def circuit_breaker(self) -> CircuitBreaker:
        return self._circuit

    def reset(self) -> None:
        self._circuit = CircuitBreaker(
            failure_threshold=self._config.circuit_failure_threshold,
            window_seconds=self._config.circuit_window_seconds,
            reset_timeout=self._config.circuit_reset_timeout,
        )

    @property
    def config(self) -> LLMErrorConfig:
        return self._config

    def _fallback_message(
        self, category: ErrorCategory, *, circuit_open: bool = False
    ) -> AIMessage:
        text = self._config.fallback_responses.get(
            category,
            "模型调用失败。请稍后再试。",
        )
        suffix = ""
        if circuit_open:
            suffix = "（已触发熔断保护）"
        return AIMessage(
            content=text + suffix,
            metadata={
                "llm_error_category": category.value,
                "circuit_open": circuit_open,
                "is_fallback": True,
            },
        )

    def _compute_delay(self, attempt: int) -> float:
        delay = self._config.base_delay * (self._config.exponential_base**attempt)
        return min(delay, self._config.max_delay)

    async def _invoke_with_retry(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse[Any]]],
    ) -> tuple[ModelCallResult[Any] | None, ErrorCategory | None]:
        """Run handler with retry. Returns (result, error_category_or_none)."""
        last_category: ErrorCategory | None = None
        for attempt in range(self._config.max_retries + 1):
            try:
                result = await handler(request)
                if attempt > 0:
                    self._circuit.record_success()
                return result, None
            except GraphBubbleUp:
                raise
            except Exception as exc:
                category = classify_error(exc)
                last_category = category
                if category == ErrorCategory.CONTROL_FLOW:
                    raise
                if category not in _RETRYABLE_CATEGORIES:
                    # Non-retryable; do not count toward circuit breaker for
                    # user errors like auth, but still record one failure
                    # so a sustained 401 storm eventually opens the circuit.
                    self._circuit.record_failure()
                    return None, category
                if attempt >= self._config.max_retries:
                    self._circuit.record_failure()
                    return None, category
                delay = self._compute_delay(attempt)
                logger.warning(
                    "LLM call failed (attempt %d/%d, category=%s): %r. Retrying in %.2fs",
                    attempt + 1,
                    self._config.max_retries + 1,
                    category.value,
                    exc,
                    delay,
                )
                self._circuit.record_failure()
                if delay > 0:
                    await asyncio.sleep(delay)
        return None, last_category  # pragma: no cover — unreachable

    @override
    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse[Any]]],
    ) -> ModelCallResult[Any]:
        if not self._config.enabled:
            return await handler(request)

        if not self._circuit.allow_request():
            logger.warning("Circuit breaker open: short-circuiting LLM call to fallback")
            return self._fallback_message(ErrorCategory.TRANSIENT, circuit_open=True)

        result, error_category = await self._invoke_with_retry(request, handler)
        if result is not None:
            return result
        # Failure path
        assert error_category is not None  # invariant from _invoke_with_retry
        return self._fallback_message(
            error_category, circuit_open=self._circuit.state == CircuitState.OPEN
        )

    @override
    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Any],
    ) -> Any:
        if not self._config.enabled:
            return handler(request)
        # Sync variant: single attempt, classify on failure, surface fallback.
        # No backoff sleep here — sleeping in a sync path would block the
        # caller, and the async path (awrap_model_call) already owns
        # retry+exponential-backoff. The sync path is not on the current
        # call graph but kept for API completeness and parity of fallback
        # behavior.
        try:
            return handler(request)
        except GraphBubbleUp:
            raise
        except Exception as exc:
            category = classify_error(exc)
            if category == ErrorCategory.CONTROL_FLOW:
                raise
            return self._fallback_message(category)
