"""Enum utilities."""

from enum import StrEnum
from typing import Any, TypeVar

EnumT = TypeVar("EnumT", bound=StrEnum)


def get_external_name(enum_name: str) -> str:
    return enum_name.replace("_", " ").title()


class NameValueStrEnum(StrEnum):
    """
    A NameValueStrEnum is a StrEnum where the value must be exactly same as the name.
    """

    def __init__(self, value: str):
        super().__init__()
        if value != self.name:
            raise TypeError(
                f"Member value must be the same as its name since "
                f"EnumClass[{self.__class__.__qualname__}] inherits `NameValueStrEnum`. "
                f"But found value[{value}] != name[{self.name}]"
            )

    @staticmethod
    def _generate_next_value_(name: str, start: Any, count: int, last_values: Any) -> str:
        return name
