"""Memory configuration (P4.6).

Boot-time configuration for the memory evolution subsystem. Ported from
deer-flow's `config/memory_config.py` schema, adapted to quant-agent's
pydantic-settings `Settings` (D3: boot-time config lives in settings.py).

These values gate the MemoryUpdater (confidence threshold, max facts,
guaranteed categories), the MemoryUpdateQueue (per-thread debounce), and
the DynamicContextMiddleware memory injection (injection_enabled,
max_injection_tokens, token_counting).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class MemoryConfig(BaseModel):
    """Memory subsystem configuration.

    Attributes:
        injection_enabled: Whether DynamicContextMiddleware emits the
            ``{stable_id}__memory`` HumanMessage (P4.2).
        fact_confidence_threshold: Minimum confidence for a fact to be
            persisted (L2). Facts below this are dropped unless their
            category is in ``guaranteed_categories``.
        max_facts: Upper bound on stored facts per user; oldest pruned by
            ``created_at`` (L3 mitigation).
        guaranteed_categories: Categories that bypass the confidence
            threshold (e.g. ``correction`` — user corrections are always
            kept).
        max_injection_tokens: Token budget cap on the injected memory
            block (L1).
        token_counting: Token counter implementation; ``tiktoken`` for
            OpenAI-compatible encodings, ``none`` to skip budgeting.
        update_debounce_seconds: Per-thread debounce window for the
            MemoryUpdateQueue (P4.5).
        max_messages_threshold: Message count that triggers the
            MemoryMiddleware write-back hook (P4.4) / SummarizationEvent.
    """

    injection_enabled: bool = True
    fact_confidence_threshold: float = 0.7
    max_facts: int = 100
    guaranteed_categories: list[str] = Field(default_factory=lambda: ["correction"])
    max_injection_tokens: int = 1024
    token_counting: Literal["tiktoken", "none"] = "tiktoken"
    update_debounce_seconds: float = 30.0
    max_messages_threshold: int = 50

    model_config = {"frozen": True}
