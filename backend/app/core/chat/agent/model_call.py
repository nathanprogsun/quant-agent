"""Model-call request carrier for the awrap_model_call hook surface.

A lightweight, mutable container passed through ``AgentMiddleware.awrap_model_call``.
Middlewares may replace ``messages`` (and, in future, ``tools``) before
delegating to the handler. Mutability is intentional: the request is a
transient call-site carrier, not domain state.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from langchain_core.messages import BaseMessage


@dataclass
class ModelCallRequest:
    """Carrier for the model call: messages + bound tools."""

    messages: list[BaseMessage] = field(default_factory=list)
    tools: list[Any] | None = None
