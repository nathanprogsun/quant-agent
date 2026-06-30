"""Tests for MemoryConfig defaults and Settings wiring (P4.6)."""

from __future__ import annotations

from app.config.memory_config import MemoryConfig
from app.settings import Settings


def test_memory_config_defaults() -> None:
    cfg = MemoryConfig()
    assert cfg.fact_confidence_threshold == 0.7
    assert cfg.max_facts == 100
    assert cfg.guaranteed_categories == ["correction"]
    assert cfg.max_injection_tokens > 0
    assert cfg.token_counting == "tiktoken"


def test_memory_config_injection_enabled_default_true() -> None:
    # deer-flow default: memory injection is on.
    assert MemoryConfig().injection_enabled is True


def test_memory_config_debounce_defaults() -> None:
    cfg = MemoryConfig()
    # Queue debounce is 30s per spec.
    assert cfg.update_debounce_seconds == 30.0
    assert cfg.max_messages_threshold > 0


def test_settings_exposes_memory_config() -> None:
    settings = Settings()
    assert isinstance(settings.memory, MemoryConfig)
    assert settings.memory.fact_confidence_threshold == 0.7
    assert settings.memory.max_facts == 100
    assert settings.memory.token_counting == "tiktoken"
