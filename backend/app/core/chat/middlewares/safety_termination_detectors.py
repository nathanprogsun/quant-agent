"""Safety-termination detection — provider-agnostic.

Different model providers encode "the model refused to answer for safety
reasons" in different fields. This module defines a Protocol plus a few
built-in detectors so the rest of the system can treat safety termination
uniformly.

Mirrors legacy ``safety_termination_detectors.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from langchain_core.messages import AIMessage


@dataclass(frozen=True)
class SafetyTermination:
    """Result of a safety-termination detection."""

    detector: str
    reason: str
    detail: str | None = None


@runtime_checkable
class SafetyTerminationDetector(Protocol):
    """Provider-agnostic detector for safety-refusal responses.

    Implementations inspect ``message`` and return ``None`` when no
    safety termination is detected, otherwise a ``SafetyTermination``.
    """

    name: str

    def detect(self, message: AIMessage) -> SafetyTermination | None: ...


class OpenAICompatibleContentFilterDetector:
    """Detects ``finish_reason='content_filter'`` (OpenAI / vLLM / Moonshot)."""

    name = "openai_content_filter"

    def detect(self, message: AIMessage) -> SafetyTermination | None:
        metadata = getattr(message, "response_metadata", {}) or {}
        finish_reason = metadata.get("finish_reason")
        if finish_reason == "content_filter":
            return SafetyTermination(
                detector=self.name,
                reason="content_filter",
                detail="Provider flagged the response as content_filter",
            )
        return None


class AnthropicRefusalDetector:
    """Detects Anthropic's ``stop_reason='refusal'``."""

    name = "anthropic_refusal"

    def detect(self, message: AIMessage) -> SafetyTermination | None:
        metadata = getattr(message, "response_metadata", {}) or {}
        stop_reason = metadata.get("stop_reason")
        if stop_reason == "refusal":
            return SafetyTermination(
                detector=self.name,
                reason="refusal",
                detail="Anthropic returned stop_reason=refusal",
            )
        return None


class GeminiSafetyDetector:
    """Detects Gemini's ``finishReason='SAFETY'``."""

    name = "gemini_safety"

    _SAFETY_TOKENS = ("SAFETY", "BLOCKLIST", "PROHIBITED_CONTENT")

    def detect(self, message: AIMessage) -> SafetyTermination | None:
        metadata = getattr(message, "response_metadata", {}) or {}
        # Gemini typically nests metadata under 'usage_metadata' or top-level keys.
        candidates: list[Any] = [
            metadata.get("finishReason"),
            metadata.get("finish_reason"),
            (metadata.get("candidates") or [{}])[0].get("finishReason")
            if isinstance(metadata.get("candidates"), list) and metadata.get("candidates")
            else None,
        ]
        for c in candidates:
            if isinstance(c, str) and c in self._SAFETY_TOKENS:
                return SafetyTermination(
                    detector=self.name,
                    reason=c.lower(),
                    detail=f"Gemini finishReason={c}",
                )
        return None


def default_detectors() -> list[SafetyTerminationDetector]:
    """Return the built-in detector set."""
    return [
        OpenAICompatibleContentFilterDetector(),
        AnthropicRefusalDetector(),
        GeminiSafetyDetector(),
    ]


__all__ = [
    "AnthropicRefusalDetector",
    "GeminiSafetyDetector",
    "OpenAICompatibleContentFilterDetector",
    "SafetyTermination",
    "SafetyTerminationDetector",
    "default_detectors",
]
