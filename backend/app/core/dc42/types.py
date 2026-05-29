"""DC42 data types."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class StrategyChunk:
    """A chunk of DC42 strategy knowledge."""
    chunk_id: str
    strategy_id: str
    chunk_type: str  # intent, factor, parameter, experience
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RetrievalResult:
    """Result from DC42 intent-based retrieval."""
    chunks: list[StrategyChunk]
    strategy_names: list[str]
    summary: str


@dataclass(frozen=True)
class ParameterAnalysis:
    """DC42 parameter range analysis."""
    parameter: str
    user_value: float
    dc42_p10: float
    dc42_p50: float
    dc42_p90: float
    in_range: bool
    recommendation: str


@dataclass(frozen=True)
class SimilarCase:
    """A similar strategy from DC42."""
    strategy_id: str
    strategy_name: str
    similarity_score: float
    summary: str
    key_differences: list[str]


@dataclass(frozen=True)
class Diagnosis:
    """DC42 failure diagnosis."""
    error_type: str
    likely_causes: list[str]
    dc42_examples: list[str]
    fix_suggestions: list[str]
