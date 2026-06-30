"""Skill-specific exceptions."""

from __future__ import annotations


class SkillError(Exception):
    """Base for all skill subsystem errors."""


class SkillParseError(SkillError):
    """YAML frontmatter malformed or unreadable."""


class SkillValidationError(SkillError):
    """Required field missing or invalid value."""


class SkillNotFoundError(SkillError):
    """Skill name not present in registry."""


class SkillPathTraversalError(SkillError):
    """Attempt to read outside container_path."""
