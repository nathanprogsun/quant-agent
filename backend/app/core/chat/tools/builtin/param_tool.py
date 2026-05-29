"""Parameter validation agent tool — DC42 range guard."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ParameterValidationResult:
    warnings: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)


def validate_parameters(
    params: dict[str, Any],
    dc42_ranges: dict[str, dict[str, float]],
) -> ParameterValidationResult:
    """Validate strategy parameters against DC42 ranges."""
    warnings: list[str] = []
    suggestions: list[str] = []

    for key, value in params.items():
        if not isinstance(value, (int, float)):
            continue

        ranges = dc42_ranges.get(key)
        if not ranges:
            continue

        p10 = ranges.get("P10", 0)
        p90 = ranges.get("P90", float("inf"))

        if value < p10:
            warnings.append(f"参数 {key}={value} 低于 DC42 P10 ({p10})，建议调高")
            suggestions.append(f"将 {key} 调整到 {p10}-{p90} 范围内")
        elif value > p90:
            warnings.append(f"参数 {key}={value} 超过 DC42 P90 ({p90})，建议调低")
            suggestions.append(f"将 {key} 调整到 {p10}-{p90} 范围内")

    return ParameterValidationResult(warnings=warnings, suggestions=suggestions)
