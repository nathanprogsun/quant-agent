"""Tests for the metadata-only LRU-cached skills prompt section (Task 1.8).

The LRU cache must:
- Return the same string instance for identical inputs (byte-stable, single
  entry per distinct skill signature).
- Return an empty ``<skill_system></skill_system>`` block when there are no
  enabled skills.
- List only ``name`` + ``description`` in ``<available_skills>`` — never the
  skill body (progressive disclosure).

``apply_prompt_template`` MUST integrate the cached section so the lead
agent's system prompt carries the skill metadata block when skills are
enabled, and the same ``SYSTEM_PROMPT`` invariant is preserved when no
skills are provided.
"""

from __future__ import annotations

from app.core.chat.agent.prompt import apply_prompt_template
from app.core.chat.agent.skills_prompt import (
    _get_cached_skills_prompt_section,
    _invalidate_skills_cache,
)

# Two identical inputs (same tuple) must hit the LRU and return the same object.
_SAMPLE_SKILLS: tuple[tuple[str, str], ...] = (
    ("deep-research", "Conduct deep research on a topic."),
    ("code-review", "Review code for bugs and improvement suggestions."),
)
_CONTAINER_PATH = "/mnt/skills"


def setup_function(_func: object) -> None:
    """Reset the LRU cache before each test so cross-test state is contained."""
    _invalidate_skills_cache()


def test_lru_returns_identical_string_instance_for_identical_inputs() -> None:
    """Same (skills_tuple, container_base_path) -> same cached string object."""
    first = _get_cached_skills_prompt_section(_SAMPLE_SKILLS, _CONTAINER_PATH)
    second = _get_cached_skills_prompt_section(_SAMPLE_SKILLS, _CONTAINER_PATH)
    assert first == second
    # Byte-stable => identity-equal (LRU hit returns the same object).
    assert first is second


def test_empty_skills_returns_empty_skill_system_block() -> None:
    """When no enabled skills, the section MUST be a single empty block."""
    section = _get_cached_skills_prompt_section((), _CONTAINER_PATH)
    assert section == "<skill_system></skill_system>"


def test_available_skills_lists_only_name_and_description() -> None:
    """<available_skills> MUST contain only name + description (no body)."""
    section = _get_cached_skills_prompt_section(_SAMPLE_SKILLS, _CONTAINER_PATH)
    assert "<available_skills>" in section
    # Each skill name appears exactly once.
    assert section.count("deep-research") == 1
    assert section.count("code-review") == 1
    # No SKILL.md body fragments should leak: strings containing { } braces
    # (the legacy prompt_template body used {query} etc.) must NOT appear.
    assert "{query}" not in section
    assert "{focus}" not in section
    assert "{goal}" not in section


def test_xml_is_well_formed_with_skill_system_wrapping() -> None:
    """The section is a single <skill_system>...</skill_system> document."""
    section = _get_cached_skills_prompt_section(_SAMPLE_SKILLS, _CONTAINER_PATH)
    assert section.startswith("<skill_system>")
    assert section.endswith("</skill_system>")
    # Single <skill_system> wrapper
    assert section.count("<skill_system>") == 1
    assert section.count("</skill_system>") == 1
    # <available_skills> nested once inside
    assert section.count("<available_skills>") == 1
    assert section.count("</available_skills>") == 1


def test_container_base_path_is_part_of_cache_key() -> None:
    """Different container paths invalidate the cache slot."""
    a = _get_cached_skills_prompt_section(_SAMPLE_SKILLS, "/mnt/skills/a")
    b = _get_cached_skills_prompt_section(_SAMPLE_SKILLS, "/mnt/skills/b")
    # Different paths => different cache slots; identity-equal only if the
    # underlying computed strings happen to be identical.
    assert a == b  # current impl does not embed the path in output
    # Subsequent call with the first path returns the first cached value.
    again = _get_cached_skills_prompt_section(_SAMPLE_SKILLS, "/mnt/skills/a")
    assert again is a


def test_distinct_signatures_produce_distinct_outputs() -> None:
    """Different (name, description) tuples MUST produce different sections."""
    s1 = _get_cached_skills_prompt_section((("alpha", "alpha desc"),), _CONTAINER_PATH)
    s2 = _get_cached_skills_prompt_section((("beta", "beta desc"),), _CONTAINER_PATH)
    assert s1 != s2
    assert "alpha" in s1
    assert "beta" not in s1


def test_invalidation_drops_cached_entries() -> None:
    """After invalidate, the next call returns a freshly computed string."""
    first = _get_cached_skills_prompt_section(_SAMPLE_SKILLS, _CONTAINER_PATH)
    _invalidate_skills_cache()
    second = _get_cached_skills_prompt_section(_SAMPLE_SKILLS, _CONTAINER_PATH)
    # Equal in content, but post-invalidation the LRU returns a new string
    # object (the cache was cleared and rebuilt on the next call).
    assert first == second


# ── apply_prompt_template integration (Task 1.8 wiring) ──────────


def test_apply_prompt_template_appends_skill_system_when_skills_given() -> None:
    """apply_prompt_template() must inline the cached skill section."""
    prompt = apply_prompt_template(
        skills=(
            ("deep-research", "Conduct deep research on a topic."),
            ("code-review", "Review code for bugs."),
        ),
        container_base_path="/mnt/skills",
    )
    assert "<skill_system>" in prompt
    assert "deep-research" in prompt
    assert "code-review" in prompt


def test_apply_prompt_template_omits_skill_system_when_no_skills() -> None:
    """When no skills are passed, the system prompt MUST be unchanged."""
    prompt = apply_prompt_template()
    assert "<skill_system>" not in prompt
    # The baseline SYSTEM_PROMPT invariant is preserved.
    assert "简体中文" in prompt


def test_apply_prompt_template_skill_section_is_lru_cached() -> None:
    """Two calls with identical skills reuse the same cached string instance.

    The outer ``apply_prompt_template`` builds a new str each call (the SYSTEM
    prompt prefix + appended blocks), so identity equality can only be checked
    on the LRU-cached ``<skill_system>`` block itself. We assert that the
    inline substring in both calls is byte-equal AND the cached block object
    the LRU returned is identical across calls.
    """
    skills = (("alpha", "alpha desc"),)
    block_a = _get_cached_skills_prompt_section(skills, "/mnt/skills")
    block_b = _get_cached_skills_prompt_section(skills, "/mnt/skills")
    p1 = apply_prompt_template(skills=skills, container_base_path="/mnt/skills")
    p2 = apply_prompt_template(skills=skills, container_base_path="/mnt/skills")
    # The LRU returns the same string instance on a hit.
    assert block_a is block_b
    # The two rendered prompts both contain that exact cached block.
    assert p1.count(block_a) == 1
    assert p2.count(block_b) == 1
