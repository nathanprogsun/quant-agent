"""Skill domain types."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class SkillCategory(StrEnum):
    PUBLIC = "public"
    CUSTOM = "custom"


@dataclass
class Skill:
    """Metadata-only skill record. Body is loaded on demand via read_file_tool."""

    name: str
    description: str
    category: SkillCategory
    container_path: str
    license: str | None = None
    allowed_tools: list[str] = field(default_factory=list)
    enabled: bool = True
    body: str | None = None  # populated only by read_body()
