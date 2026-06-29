"""Validation utilities."""

from typing import Any


def not_none[T](any_value: T | None) -> T:
    if any_value is None:
        raise ValueError("expected value to present")
    return any_value


def count_not_none(*values: Any | None) -> int:
    return sum(0 if v is None else 1 for v in values)


def one_row_only[T](values: list[T]) -> T:
    if len(values) != 1:
        raise ValueError(f"expected exactly one row, got {len(values)}")
    return values[0]


def one_row_or_none[T](values: list[T]) -> T | None:
    if len(values) > 1:
        raise ValueError(f"expected at most one row, got {len(values)}")
    return values[0] if values else None
