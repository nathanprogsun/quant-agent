"""Model-call request carrier for the ``awrap_model_call`` hook surface.

Originally a hand-rolled shim used by the manual ``StateGraph`` agent node
*before* the migration to ``langchain.agents.create_agent``. Now kept as a
minimal test fixture: at runtime the middleware chain receives langchain's
native ``ModelRequest`` (which has ``.override()``); tests construct
``ModelCallRequest`` because its constructor needs only ``messages``/``tools``
(no live ``model``). To keep middleware code paths exercised identically in
both runtime and unit tests, this shim implements ``override()`` with the
same semantics as ``ModelRequest.override`` — return a new instance with the
supplied fields replaced.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

from langchain_core.messages import BaseMessage


@dataclass
class ModelCallRequest:
    """Carrier for the model call: messages + bound tools (optional state)."""

    messages: list[BaseMessage] = field(default_factory=list)
    tools: list[Any] | None = None
    state: dict[str, Any] | None = None

    def override(self, **updates: Any) -> ModelCallRequest:
        """Return a new instance with the supplied fields replaced.

        Mirrors ``ModelRequest.override`` so middleware code that calls
        ``request.override(messages=...)`` / ``request.override(tools=...)``
        works uniformly against native ``ModelRequest`` (runtime) and this
        shim (unit tests).
        """
        return replace(self, **updates)
