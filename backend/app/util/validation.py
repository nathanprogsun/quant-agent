"""Validation utilities."""

from typing import Any, TypeVar

AnyT = TypeVar("AnyT", bound=Any)


def not_none(any_value: AnyT | None) -> AnyT:
    if any_value is None:
        raise ValueError("expected value to present")
    return any_value


def count_not_none(*values: Any | None) -> int:
    return sum(0 if v is None else 1 for v in values)


def one_row_only(values: list[AnyT]) -> AnyT:
    if len(values) != 1:
        raise ValueError(f"expected exactly one row, got {len(values)}")
    return values[0]


def one_row_or_none(values: list[AnyT]) -> AnyT | None:
    if len(values) > 1:
        raise ValueError(f"expected at most one row, got {len(values)}")
    return values[0] if values else None
