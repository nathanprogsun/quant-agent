"""Safety finish-reason middleware.

When the model response was terminated by the provider's safety filter
(content_filter, refusal, SAFETY, …), this middleware clears the
``tool_calls`` on the AIMessage so the agent loop ends instead of
dispatching tool calls against a refused answer, and tags the message
with ``metadata.safety_terminated`` so downstream consumers can react.

Detection is delegated to pluggable ``SafetyTerminationDetector``
implementations (see ``safety_termination_detectors.py``).
"""

from __future__ import annotations

import logging
from copy import deepcopy
from typing import Any, override

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import AIMessage, BaseMessage
from langgraph.runtime import Runtime

from app.core.chat.middlewares.safety_termination_detectors import (
    SafetyTermination,
    SafetyTerminationDetector,
    default_detectors,
)

logger = logging.getLogger(__name__)


def _strip_tool_calls(message: AIMessage, termination: SafetyTermination) -> AIMessage:
    additional = dict(getattr(message, "additional_kwargs", {}) or {})
    for key in ("tool_calls", "function_call"):
        additional.pop(key, None)
    response_metadata = deepcopy(getattr(message, "response_metadata", {}) or {})
    if response_metadata.get("finish_reason") == "tool_calls":
        response_metadata["finish_reason"] = "stop"
    metadata = dict(getattr(message, "metadata", {}) or {})
    metadata["safety_terminated"] = True
    metadata["safety_detector"] = termination.detector
    metadata["safety_reason"] = termination.reason
    if termination.detail:
        metadata["safety_detail"] = termination.detail
    return message.model_copy(
        update={
            "tool_calls": [],
            "invalid_tool_calls": [],
            "additional_kwargs": additional,
            "response_metadata": response_metadata,
            "metadata": metadata,
        }
    )


class SafetyFinishReasonMiddleware(AgentMiddleware[AgentState]):
    """Suppress tool calls and tag messages when safety termination fires."""

    def __init__(
        self,
        *,
        enabled: bool = True,
        detectors: list[SafetyTerminationDetector] | None = None,
    ) -> None:
        super().__init__()
        self._enabled = enabled
        self._detectors: list[SafetyTerminationDetector] = (
            detectors if detectors is not None else default_detectors()
        )

    @property
    def detectors(self) -> list[SafetyTerminationDetector]:
        return list(self._detectors)

    @override
    def after_model(
        self, state: AgentState, runtime: Runtime
    ) -> dict[str, Any] | None:
        return self._apply(state)

    @override
    async def aafter_model(
        self, state: AgentState, runtime: Runtime
    ) -> dict[str, Any] | None:
        return self._apply(state)

    def _apply(self, state: AgentState) -> dict[str, Any] | None:
        """Shared sync/async implementation of the safety-termination check."""
        if not self._enabled:
            return None
        messages: list[BaseMessage] = list(state.get("messages", []))
        if not messages:
            return None
        last = messages[-1]
        if not isinstance(last, AIMessage):
            return None
        for det in self._detectors:
            try:
                termination = det.detect(last)
            except Exception:
                logger.exception("Safety detector %s raised", getattr(det, "name", "?"))
                continue
            if termination is None:
                continue
            logger.info(
                "Safety termination detected (%s): %s",
                termination.detector,
                termination.reason,
            )
            stripped = _strip_tool_calls(last, termination)
            return {"messages": [*messages[:-1], stripped]}
        return None
