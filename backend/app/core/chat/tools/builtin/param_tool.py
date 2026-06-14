"""Parameter validation agent tool — DC42 range guard."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from langchain_core.tools import BaseTool, tool

from app.core.dc42.paths import DEFAULT_PARAMETER_LIMITS_PATH


@dataclass(frozen=True)
class ParameterValidationResult:
    warnings: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)


def validation_result_to_dict(result: ParameterValidationResult) -> dict[str, Any]:
    """Convert ParameterValidationResult to a JSON-serializable dict."""
    return {
        "warnings": list(result.warnings),
        "suggestions": list(result.suggestions),
    }


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


def load_default_dc42_ranges() -> dict[str, dict[str, float]]:
    """Load committed DC42 parameter limits for agent tool validation."""
    if not DEFAULT_PARAMETER_LIMITS_PATH.is_file():
        return {}
    return json.loads(DEFAULT_PARAMETER_LIMITS_PATH.read_text(encoding="utf-8"))


def make_validate_parameters_tool(
    dc42_ranges: dict[str, dict[str, float]] | None = None,
) -> BaseTool:
    """Create a LangChain tool that validates params against DC42 ranges."""
    ranges = dc42_ranges if dc42_ranges is not None else load_default_dc42_ranges()

    @tool
    def validate_strategy_parameters(params: dict[str, Any]) -> dict[str, Any]:
        """Validate strategy parameters against DC42 historical percentile ranges."""
        return validation_result_to_dict(validate_parameters(params, ranges))

    return validate_strategy_parameters
