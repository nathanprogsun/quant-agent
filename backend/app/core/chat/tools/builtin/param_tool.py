"""Parameter validation agent tool."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from langchain_core.tools import BaseTool, tool


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


def validate_parameters(params: dict[str, Any]) -> ParameterValidationResult:
    """Validate strategy parameters with basic sanity checks."""
    warnings: list[str] = []
    suggestions: list[str] = []

    for key, value in params.items():
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            continue

        if value < 0:
            warnings.append(f"参数 {key}={value} 为负数，通常不合理")
            suggestions.append(f"将 {key} 调整为非负数")
        elif value == 0 and key in {"stock_count", "lookback", "window", "n"}:
            warnings.append(f"参数 {key}={value} 为 0，可能导致策略无持仓或无计算样本")
            suggestions.append(f"将 {key} 调整为正整数")

    return ParameterValidationResult(warnings=warnings, suggestions=suggestions)


def make_validate_parameters_tool() -> BaseTool:
    """Create a LangChain tool that validates strategy parameters."""

    @tool
    def validate_strategy_parameters(params: dict[str, Any]) -> dict[str, Any]:
        """Validate strategy parameters with basic sanity checks."""
        return validation_result_to_dict(validate_parameters(params))

    return validate_strategy_parameters
