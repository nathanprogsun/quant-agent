"""Metadata-only skills prompt section with LRU cache.

Builds the ``<skill_system>`` block injected into the system prompt. Lists
only skill name + description (progressive disclosure — the body is loaded
on demand via the read_file tool). The section is byte-stable for identical
inputs so the prefix cache reuses it across turns.

Call ``_invalidate_skills_cache()`` after a toggle/write to drop the LRU
entry so the next prompt assembly reflects the new state.
"""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable
from functools import lru_cache

_SKILL_SYSTEM_OPEN = "<skill_system>"
_SKILL_SYSTEM_CLOSE = "</skill_system>"
_AVAILABLE_OPEN = "<available_skills>"
_AVAILABLE_CLOSE = "</available_skills>"
_MAX_LRU_ENTRIES = 32


def _format_skill_entry(name: str, description: str) -> str:
    """Format a single skill as a metadata-only XML entry (no body)."""
    return f'<skill name="{name}">{description}</skill>'


@lru_cache(maxsize=_MAX_LRU_ENTRIES)
def _get_cached_skills_prompt_section(
    skills_tuple: tuple[tuple[str, str], ...],
    container_base_path: str,
) -> str:
    """Return the cached ``<skill_system>`` block for the given skills.

    Args:
        skills_tuple: Tuple of (name, description) pairs — metadata only.
        container_base_path: Base path of the skill storage (part of the cache
            key so two storage roots do not share a cache slot).

    Returns:
        Byte-stable string. Empty ``<skill_system></skill_system>`` when no
        enabled skills.
    """
    _ = container_base_path  # cache-key only; not emitted
    if not skills_tuple:
        return f"{_SKILL_SYSTEM_OPEN}{_SKILL_SYSTEM_CLOSE}"
    entries = "".join(_format_skill_entry(name, desc) for name, desc in skills_tuple)
    return f"{_SKILL_SYSTEM_OPEN}{_AVAILABLE_OPEN}{entries}{_AVAILABLE_CLOSE}{_SKILL_SYSTEM_CLOSE}"


# Invalidation registry: toggle API (P1.5) registers a callback to clear the
# LRU entry when a skill is enabled/disabled.
_invalidation_callbacks: OrderedDict[int, Callable[[], None]] = OrderedDict()


def register_skills_cache_invalidator(callback: Callable[[], None]) -> None:
    """Register a callback fired when the skills cache is invalidated."""
    _invalidation_callbacks[id(callback)] = callback


def _invalidate_skills_cache() -> None:
    """Drop all cached skills prompt sections and notify registrants."""
    _get_cached_skills_prompt_section.cache_clear()
    for cb in list(_invalidation_callbacks.values()):
        cb()
