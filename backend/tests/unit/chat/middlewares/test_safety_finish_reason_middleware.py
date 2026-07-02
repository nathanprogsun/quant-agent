"""Tests for safety termination detectors + SafetyFinishReasonMiddleware."""

from __future__ import annotations

from typing import Any

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from app.core.chat.middlewares.safety_finish_reason_middleware import (
    SafetyFinishReasonMiddleware,
)
from app.core.chat.middlewares.safety_termination_detectors import (
    AnthropicRefusalDetector,
    GeminiSafetyDetector,
    OpenAICompatibleContentFilterDetector,
    default_detectors,
)

# ───────────── detectors ─────────────


def test_openai_content_filter_detected() -> None:
    msg = AIMessage(content="...", response_metadata={"finish_reason": "content_filter"})
    det = OpenAICompatibleContentFilterDetector()
    out = det.detect(msg)
    assert out is not None
    assert out.reason == "content_filter"
    assert out.detector == "openai_content_filter"


def test_openai_normal_stop_not_flagged() -> None:
    msg = AIMessage(content="...", response_metadata={"finish_reason": "stop"})
    assert OpenAICompatibleContentFilterDetector().detect(msg) is None


def test_anthropic_refusal_detected() -> None:
    msg = AIMessage(content="...", response_metadata={"stop_reason": "refusal"})
    out = AnthropicRefusalDetector().detect(msg)
    assert out is not None
    assert out.reason == "refusal"


def test_anthropic_normal_end_not_flagged() -> None:
    msg = AIMessage(content="...", response_metadata={"stop_reason": "end_turn"})
    assert AnthropicRefusalDetector().detect(msg) is None


def test_gemini_safety_detected() -> None:
    msg = AIMessage(content="...", response_metadata={"finishReason": "SAFETY"})
    out = GeminiSafetyDetector().detect(msg)
    assert out is not None
    assert out.reason == "safety"


def test_gemini_normal_stop_not_flagged() -> None:
    msg = AIMessage(content="...", response_metadata={"finishReason": "STOP"})
    assert GeminiSafetyDetector().detect(msg) is None


def test_default_detectors_returns_all_three() -> None:
    detectors = default_detectors()
    assert len(detectors) == 3
    names = {d.name for d in detectors}
    assert "openai_content_filter" in names
    assert "anthropic_refusal" in names
    assert "gemini_safety" in names


# ───────────── middleware ─────────────


@pytest.mark.asyncio
async def test_safety_termination_clears_tool_calls() -> None:
    mw = SafetyFinishReasonMiddleware()
    state = {
        "messages": [
            HumanMessage(content="hi", id="u1"),
            AIMessage(
                content="blocked",
                tool_calls=[{"name": "search", "args": {}, "id": "tc1"}],
                response_metadata={"finish_reason": "content_filter"},
            ),
        ]
    }
    out = await mw.aafter_model(state, runtime=None)  # type: ignore[arg-type]
    assert out is not None
    new_messages = out["messages"]
    assert new_messages
    last = new_messages[-1]
    assert isinstance(last, AIMessage)
    assert last.tool_calls == []
    assert last.metadata.get("safety_terminated") is True
    assert last.metadata.get("safety_reason") == "content_filter"


@pytest.mark.asyncio
async def test_normal_response_unchanged() -> None:
    mw = SafetyFinishReasonMiddleware()
    state = {
        "messages": [
            HumanMessage(content="hi", id="u1"),
            AIMessage(
                content="ok",
                tool_calls=[{"name": "search", "args": {}, "id": "tc1"}],
                response_metadata={"finish_reason": "tool_calls"},
            ),
        ]
    }
    out = await mw.aafter_model(state, runtime=None)  # type: ignore[arg-type]
    assert out is None


@pytest.mark.asyncio
async def test_disabled_middleware_is_noop() -> None:
    mw = SafetyFinishReasonMiddleware(enabled=False)
    state = {
        "messages": [
            HumanMessage(content="hi", id="u1"),
            AIMessage(
                content="blocked",
                tool_calls=[{"name": "x", "args": {}, "id": "tc1"}],
                response_metadata={"finish_reason": "content_filter"},
            ),
        ]
    }
    assert await mw.aafter_model(state, runtime=None) is None  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_custom_detector_set() -> None:
    """When custom detectors are provided, only those are used."""

    class _AlwaysFalse:
        name = "always_false"

        def detect(self, message: AIMessage) -> Any:
            return None

    mw = SafetyFinishReasonMiddleware(detectors=[_AlwaysFalse()])  # type: ignore[list-item]
    state = {
        "messages": [
            HumanMessage(content="hi", id="u1"),
            AIMessage(
                content="blocked",
                response_metadata={"finish_reason": "content_filter"},
            ),
        ]
    }
    out = await mw.aafter_model(state, runtime=None)  # type: ignore[arg-type]
    # No detection, no mutation
    assert out is None
