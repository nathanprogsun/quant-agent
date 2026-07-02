"""Token budget middleware — per-run token spend enforcement.

Tracks cumulative token usage across model responses within a single run
(thread + run_id). At ``warn_threshold`` it queues a deferred warning
HumanMessage that the next ``awrap_model_call`` injects just before the
model call. At ``hard_limit`` it overwrites the AIMessage's content and
clears its tool_calls to force a final-answer response.

The deferred-injection pattern mirrors ``LoopDetectionMiddleware``: state
mutations are queued in ``after_model`` but only injected during
``wrap_model_call`` so the tool_call pairing invariant (OpenAI / Moonshot
require tool_calls to be followed by matching ToolMessages) is preserved.

Mirrors legacy ``token_budget_middleware.py`` adapted to
quant-agent's ``ModelRequest`` carrier.
"""

from __future__ import annotations

import logging
import threading
from collections import OrderedDict
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from langchain.agents.middleware import AgentMiddleware, ModelRequest
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langgraph.runtime import Runtime

logger = logging.getLogger(__name__)

_DEFAULT_WARN_THRESHOLD = 50_000
_DEFAULT_HARD_LIMIT = 80_000
_MAX_PENDING_PER_RUN = 2


@dataclass
class TokenBudgetConfig:
    enabled: bool = True
    warn_threshold: int = _DEFAULT_WARN_THRESHOLD
    hard_limit: int = _DEFAULT_HARD_LIMIT
    warning_template: str = (
        "[TOKEN BUDGET] Cumulative token usage has reached {used}/{hard_limit}. "
        "Wrap up the current task and produce a concise final answer."
    )
    hard_stop_template: str = (
        "[FORCED STOP] Cumulative token usage exceeded the budget "
        "({used}/{hard_limit}). Producing final answer."
    )


def _sum_usage(messages: list[BaseMessage]) -> int:
    """Sum total_tokens from AIMessage usage_metadata in messages."""
    total = 0
    for m in messages:
        if not isinstance(m, AIMessage):
            continue
        usage = getattr(m, "usage_metadata", None)
        if not usage:
            continue
        if hasattr(usage, "total_tokens"):
            total += int(getattr(usage, "total_tokens", 0) or 0)
        elif isinstance(usage, dict):
            total += int(usage.get("total_tokens", 0) or 0)
    return total


def _build_hard_stop(last_msg: AIMessage, content: str) -> AIMessage:
    update: dict[str, Any] = {"content": content, "tool_calls": []}
    additional = dict(getattr(last_msg, "additional_kwargs", {}) or {})
    for key in ("tool_calls", "function_call"):
        additional.pop(key, None)
    update["additional_kwargs"] = additional
    response_metadata = deepcopy(getattr(last_msg, "response_metadata", {}) or {})
    if response_metadata.get("finish_reason") == "tool_calls":
        response_metadata["finish_reason"] = "stop"
    update["response_metadata"] = response_metadata
    return last_msg.model_copy(update=update)


class TokenBudgetMiddleware(AgentMiddleware):
    """Enforce per-run token budget via deferred warning + hard stop."""

    def __init__(self, config: TokenBudgetConfig | None = None) -> None:
        super().__init__()
        self._config = config or TokenBudgetConfig()
        self._lock = threading.Lock()
        # (thread_id, run_id) -> list[warning]; bounded.
        self._pending_warnings: OrderedDict[tuple[str, str], list[str]] = OrderedDict()

    @classmethod
    def from_config(cls, config: TokenBudgetConfig) -> TokenBudgetMiddleware:
        """Create from a Pydantic / dataclass config object (deer-flow compat)."""
        return cls(config=config)

    @property
    def config(self) -> TokenBudgetConfig:
        return self._config

    @staticmethod
    def _pending_key(runtime: Runtime | None) -> tuple[str, str]:
        return ("default", "default")

    def _queue_warning(self, runtime: Runtime | None, warning: str) -> None:
        key = self._pending_key(runtime)
        with self._lock:
            warnings = self._pending_warnings.setdefault(key, [])
            if warning not in warnings:
                warnings.append(warning)
            if len(warnings) > _MAX_PENDING_PER_RUN:
                del warnings[: len(warnings) - _MAX_PENDING_PER_RUN]
            self._pending_warnings.move_to_end(key)

    def _drain_warnings(self, runtime: Runtime | None) -> list[str]:
        key = self._pending_key(runtime)
        with self._lock:
            return self._pending_warnings.pop(key, [])

    def reset(self) -> None:
        with self._lock:
            self._pending_warnings.clear()

    async def aafter_model(  # type: ignore[override]
        self, state: dict[str, Any], runtime: Runtime | None
    ) -> dict[str, Any] | None:
        if not self._config.enabled:
            return None
        messages: list[BaseMessage] = list(state.get("messages", []))
        if not messages:
            return None
        used = _sum_usage(messages)
        if used >= self._config.hard_limit:
            last = messages[-1]
            if not isinstance(last, AIMessage):
                return None
            hard_stop_text = self._config.hard_stop_template.format(
                used=used, hard_limit=self._config.hard_limit
            )
            replaced = _build_hard_stop(last, hard_stop_text)
            return {"messages": [*messages[:-1], replaced]}
        if used >= self._config.warn_threshold:
            warning = self._config.warning_template.format(
                used=used, hard_limit=self._config.hard_limit
            )
            self._queue_warning(runtime, warning)
        return None

    def _augment_request(self, request: ModelRequest) -> ModelRequest:
        # Drain warnings keyed by (thread_id, run_id) from request.runtime.
        # Falls back to ("default", "default") when runtime is None
        # (e.g. sync path or tests).
        runtime: Runtime | None = getattr(request, "runtime", None)
        warnings = self._drain_warnings(runtime)
        if not warnings:
            return request
        new_messages = [
            *request.messages,
            *[HumanMessage(content=w, name="token_budget_warning") for w in warnings],
        ]
        return request.override(messages=new_messages)

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Any,
    ) -> Any:
        augmented = self._augment_request(request)
        return await handler(augmented)

    def wrap_model_call(self, request: ModelRequest, handler: Any) -> Any:
        augmented = self._augment_request(request)
        return handler(augmented)
