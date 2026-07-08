"""Skill-based tool policy — filtering tools by allowed_tools union.

Each ``Skill`` can declare ``allowed_tools: list[str]``. When at least one
enabled skill specifies ``allowed_tools``, the union of those lists becomes
the active allowlist. Tools not in the allowlist are removed before
``assemble_deferred_tools`` runs.
"""

from __future__ import annotations

from typing import Any

from app.skills.types import Skill


def filter_tools_by_skill_allowed_tools(
    tools: list[Any],
    skills: list[Skill],
) -> list[Any]:
    """Remove tools not in the union of enabled skills' ``allowed_tools``.

    When no enabled skill declares ``allowed_tools``, all tools pass through.
    """
    allowed: set[str] | None = None
    for skill in skills:
        if not skill.enabled:
            continue
        if not skill.allowed_tools:
            continue
        if allowed is None:
            allowed = set()
        allowed.update(skill.allowed_tools)

    if allowed is None:
        return tools

    return [t for t in tools if tool_name(t) in allowed]


__all__ = ["filter_tools_by_skill_allowed_tools", "tool_name"]


def tool_name(t: Any) -> str | None:
    """Return the langchain tool name, falling back to ``__name__``."""
    return getattr(t, "name", None) or getattr(t, "__name__", None)
