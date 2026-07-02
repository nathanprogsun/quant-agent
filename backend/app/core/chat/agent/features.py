"""Declarative feature flags and middleware positioning decorators.

Mirrors ``deerflow.agents.features``.  ``RuntimeFeatures`` is the single
truth source that drives middleware chain assembly — callers set booleans
(or inject custom ``AgentMiddleware`` instances) and the factory calls
``_assemble_from_features`` to materialise the ordered chain.

``@Next`` / ``@Prev`` decorators allow extra middlewares to declare their
position relative to a built-in anchor.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from langchain.agents.middleware import AgentMiddleware


@dataclass
class RuntimeFeatures:
    """Declarative feature flags for ``make_lead_agent``.

    Most features accept:
    - ``True``: use the built-in default middleware
    - ``False``: disable
    - An ``AgentMiddleware`` instance: use this custom implementation

    ``summarization``, ``title``, ``token_usage``, and ``safety`` have
    no ``False`` path — they are always-on for quant-agent.
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

    # Opt-in features
    memory: bool | AgentMiddleware = False
    deferred_tool_filter: bool | AgentMiddleware = False
    subagent_limit: bool = False
    loop_detection: bool = True
    skill_activation: bool = True

    @classmethod
    def from_runnable_config(cls, configurable: dict[str, Any]) -> RuntimeFeatures:
        """Build from a langgraph ``configurable`` dict.

        Reads feature flags from the configurable payload. Unknown keys are
        silently ignored so the configurable dict can carry other runtime
        parameters.
        """
        bool_field = {f.name: f.type for f in cls.__dataclass_fields__.values()}

        kwargs: dict[str, bool] = {}
        for key, expected_type in bool_field.items():
            if key in configurable:
                val = configurable[key]
                if isinstance(val, AgentMiddleware):
                    kwargs[key] = val  # type: ignore[assignment]  # custom replacement
                elif isinstance(val, bool):
                    kwargs[key] = val
                elif isinstance(val, str):
                    kwargs[key] = val.lower() not in ("0", "false", "no", "off")
                else:
                    kwargs[key] = bool(val)
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
