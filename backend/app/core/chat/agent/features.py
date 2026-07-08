"""Declarative feature flags and middleware positioning decorators.

Mirrors ``deerflow.agents.features``.  ``RuntimeFeatures`` is the single
truth source that drives middleware chain assembly — callers set booleans
(or inject custom ``AgentMiddleware`` instances) and ``build_middlewares``
materialises the ordered chain.

``@Next`` / ``@Prev`` decorators allow extra middlewares to declare their
position relative to a built-in anchor.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from langchain.agents.middleware import AgentMiddleware


@dataclass
class RuntimeFeatures:
    """Declarative feature flags for ``make_lead_agent``.

    Most features accept:
    - ``True``: use the built-in default middleware
    - ``False``: disable
    - An ``AgentMiddleware`` instance: use this custom implementation

    ``plan_mode`` enables the ``TodoMiddleware`` for plan-mode task tracking.
    """

    # Always-on for quant-agent
    llm_error_handling: bool | AgentMiddleware = True
    input_sanitization: bool | AgentMiddleware = True
    summarization: bool | AgentMiddleware = True
    token_usage: bool | AgentMiddleware = True
    title: bool | AgentMiddleware = True
    token_budget: bool | AgentMiddleware = True
    dangling_tool_call: bool | AgentMiddleware = True
    dynamic_context: bool | AgentMiddleware = True
    system_message_coalescing: bool | AgentMiddleware = True
    safety_finish_reason: bool | AgentMiddleware = True
    clarification: bool | AgentMiddleware = True
    # Tool-call resilience: convert tool exceptions into error ToolMessages
    # and cap oversized tool outputs. Both are always-on so a single
    # ``search_jq_*`` failure or oversized retrieval result never aborts
    # the run or blows the context window.
    tool_error_handling: bool | AgentMiddleware = True
    tool_output_budget: bool | AgentMiddleware = True

    # JqPrefetch — inject jq_kb docs (API / data-dict) into context before
    # the model call so simple API/field questions don't trigger an extra
    # ``search_jq_*`` round-trip. Skips strategy (no metadata shortcut).
    jq_prefetch: bool | AgentMiddleware = True

    # Opt-in features
    memory: bool | AgentMiddleware = False
    deferred_tool_filter: bool | AgentMiddleware = False
    subagent_limit: bool = False
    loop_detection: bool | AgentMiddleware = True
    skill_activation: bool = True

    # Plan mode
    plan_mode: bool = False

    # Subagent
    subagent_enabled: bool = False

    # Reasoning
    reasoning_effort: str | None = None

    # Summarization tuning
    summarization_max_messages: int = 50

    # Custom middleware injection
    custom_middlewares: list[AgentMiddleware] = field(default_factory=list)

    @classmethod
    def from_runnable_config(cls, configurable: dict[str, Any]) -> RuntimeFeatures:
        """Build from a langgraph ``configurable`` dict.

        Reads feature flags from the configurable payload. Unknown keys are
        silently ignored so the configurable dict can carry other runtime
        parameters.
        """
        string_fields = {"reasoning_effort"}
        int_fields = {"summarization_max_messages"}
        kwargs: dict[str, Any] = {}
        for name in cls.__dataclass_fields__:
            if name == "custom_middlewares":
                continue
            if name not in configurable:
                continue
            val = configurable[name]
            if name in string_fields:
                kwargs[name] = val if isinstance(val, str) else None
            elif name in int_fields:
                kwargs[name] = (
                    int(val)
                    if isinstance(val, (int, str))
                    else cls.__dataclass_fields__[name].default
                )
            elif isinstance(val, (AgentMiddleware, bool)):
                kwargs[name] = val
            elif isinstance(val, str):
                kwargs[name] = val.lower() not in ("0", "false", "no", "off")
            else:
                kwargs[name] = bool(val)
        return cls(**kwargs)


# ---------------------------------------------------------------------------
# Middleware positioning decorators
# ---------------------------------------------------------------------------

_T = type[AgentMiddleware]


def Next(anchor: type[AgentMiddleware]) -> Callable[[_T], _T]:
    """Place this middleware immediately AFTER ``anchor`` in the chain."""
    if not issubclass(anchor, AgentMiddleware):
        raise TypeError(f"@Next expects an AgentMiddleware subclass, got {anchor!r}")

    def decorator(cls: _T) -> _T:
        cls._next_anchor = anchor  # type: ignore[attr-defined]
        return cls

    return decorator


def Prev(anchor: type[AgentMiddleware]) -> Callable[[_T], _T]:
    """Place this middleware immediately BEFORE ``anchor`` in the chain."""
    if not issubclass(anchor, AgentMiddleware):
        raise TypeError(f"@Prev expects an AgentMiddleware subclass, got {anchor!r}")

    def decorator(cls: _T) -> _T:
        cls._prev_anchor = anchor  # type: ignore[attr-defined]
        return cls

    return decorator


__all__ = ["Next", "Prev", "RuntimeFeatures"]
