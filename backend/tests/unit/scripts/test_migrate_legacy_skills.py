"""Tests for the legacy SkillRegistry migration script (Task 1.9).

The migration script must:
- Write ``skills_root/custom/<name>/SKILL.md`` for each seeded legacy skill.
- Use YAML frontmatter (name + description) parsed by ``parse_skill_file``.
- Preserve the legacy ``prompt_template`` as the SKILL.md body verbatim.
- Be idempotent: re-running produces byte-identical output.
- Skip skills that already have a SKILL.md (handled by an overwrite guard).
- Emit a sidecar manifest of migrated rows so callers can audit it.
"""

from __future__ import annotations

import importlib
import json
import warnings
from pathlib import Path

import yaml

from app.core.chat.skills import registry as legacy_registry_mod
from app.core.chat.skills.registry import SkillDefinition, SkillRegistry
from app.skills.parser import parse_skill_file
from app.skills.types import SkillCategory
from scripts.migrate_legacy_skills import migrate_legacy_skills


def _isolated_registry(tmp_path: Path) -> SkillRegistry:
    """Build a registry seeded with the same default skills as the legacy one.

    We rebuild the registry rather than import the global instance so tests
    are isolated from one another and from the real default registration.
    """
    reg = SkillRegistry()
    reg._skills.clear()
    for name, desc in [
        ("research", "Conduct deep research on a topic using web search."),
        ("code_review", "Review code for bugs, security, and improvements."),
        ("task_planning", "Break down a complex task into actionable steps."),
    ]:
        reg.register(
            SkillDefinition(
                name=name,
                description=desc,
                prompt_template=f"# {name}\nLegacy body for {name}.\n",
            )
        )
    return reg


def test_migrate_writes_skill_md_per_seeded_skill(tmp_path: Path) -> None:
    """Each seeded legacy skill gets a SKILL.md under custom/<name>/."""
    skills_root = tmp_path / "skills"
    reg = _isolated_registry(tmp_path)
    report = migrate_legacy_skills(registry=reg, skills_root=skills_root)

    for name in ("research", "code_review", "task_planning"):
        skill_md = skills_root / "custom" / name / "SKILL.md"
        assert skill_md.exists(), f"missing SKILL.md for {name}"
        # Re-parseable by parse_skill_file
        skill = parse_skill_file(skill_md, category=SkillCategory.CUSTOM)
        assert skill.name == name
    assert {r.name for r in report.records} == {
        "research",
        "code_review",
        "task_planning",
    }


def test_skill_md_has_yaml_frontmatter_with_name_and_description(tmp_path: Path) -> None:
    """The YAML frontmatter MUST contain `name` and `description`."""
    skills_root = tmp_path / "skills"
    reg = _isolated_registry(tmp_path)
    migrate_legacy_skills(registry=reg, skills_root=skills_root)

    skill_md = skills_root / "custom" / "research" / "SKILL.md"
    text = skill_md.read_text(encoding="utf-8")
    assert text.startswith("---")
    parts = text.split("---", 2)
    assert len(parts) >= 3, "SKILL.md must have a YAML frontmatter block"
    fm = yaml.safe_load(parts[1])
    assert isinstance(fm, dict)
    assert fm["name"] == "research"
    assert "description" in fm
    assert isinstance(fm["description"], str)
    assert fm["description"]  # non-empty


def test_skill_md_body_preserves_legacy_prompt_template(tmp_path: Path) -> None:
    """The body of SKILL.md MUST equal the legacy prompt_template."""
    skills_root = tmp_path / "skills"
    reg = _isolated_registry(tmp_path)
    migrate_legacy_skills(registry=reg, skills_root=skills_root)

    research = next(s for s in reg.list_all() if s.name == "research")
    expected_body = research.prompt_template
    skill_md = skills_root / "custom" / "research" / "SKILL.md"
    # Re-read with body loaded to compare verbatim
    skill = parse_skill_file(skill_md, category=SkillCategory.CUSTOM, load_body=True)
    assert skill.body == expected_body


def test_migration_report_records_are_persisted(tmp_path: Path) -> None:
    """The migration manifest MUST list every migrated skill row."""
    skills_root = tmp_path / "skills"
    reg = _isolated_registry(tmp_path)
    report = migrate_legacy_skills(registry=reg, skills_root=skills_root)

    manifest = skills_root / "custom" / "_migrated.jsonl"
    assert manifest.exists(), "expected sidecar manifest at _migrated.jsonl"
    rows = [line for line in manifest.read_text(encoding="utf-8").splitlines() if line]
    parsed = [json.loads(row) for row in rows]
    assert {r["name"] for r in parsed} == {
        "research",
        "code_review",
        "task_planning",
    }
    assert all(r["migrated"] is True for r in parsed)
    # And the returned report mirrors the persisted rows.
    assert {r.name for r in report.records} == {
        "research",
        "code_review",
        "task_planning",
    }
    assert all(r.migrated for r in report.records)


def test_migration_is_idempotent(tmp_path: Path) -> None:
    """Re-running with the same source data produces byte-identical SKILL.md."""
    skills_root = tmp_path / "skills"
    reg = _isolated_registry(tmp_path)
    migrate_legacy_skills(registry=reg, skills_root=skills_root)

    first_files = {
        name: (skills_root / "custom" / name / "SKILL.md").read_bytes()
        for name in ("research", "code_review", "task_planning")
    }
    # Re-run with a fresh registry pointing at the same source data
    reg2 = _isolated_registry(tmp_path)
    migrate_legacy_skills(registry=reg2, skills_root=skills_root)
    for name, first in first_files.items():
        again = (skills_root / "custom" / name / "SKILL.md").read_bytes()
        assert again == first, f"non-idempotent output for {name}"


def test_atomic_write_does_not_leave_temp_files_on_success(tmp_path: Path) -> None:
    """On success no ``.tmp`` siblings must remain in the per-skill dirs."""
    skills_root = tmp_path / "skills"
    reg = _isolated_registry(tmp_path)
    migrate_legacy_skills(registry=reg, skills_root=skills_root)
    for name in ("research", "code_review", "task_planning"):
        d = skills_root / "custom" / name
        leftovers = [p.name for p in d.iterdir() if p.name.endswith(".tmp")]
        assert not leftovers, f"leftover tmp files: {leftovers}"


def test_skips_registry_with_no_seeded_skills(tmp_path: Path) -> None:
    """An empty registry MUST NOT raise; it returns an empty report."""
    skills_root = tmp_path / "skills"
    reg = SkillRegistry()
    reg._skills.clear()
    report = migrate_legacy_skills(registry=reg, skills_root=skills_root)
    assert report.records == []
    # No manifest when nothing was migrated (audit log only when there is data).
    assert not (skills_root / "custom" / "_migrated.jsonl").exists()


def test_legacy_registry_module_carries_deprecation_notice(tmp_path: Path) -> None:
    """The legacy SkillRegistry module MUST emit a DeprecationWarning on import."""
    # Reload to re-trigger module-level warnings.
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        importlib.reload(legacy_registry_mod)
    deprecations = [w for w in caught if issubclass(w.category, DeprecationWarning)]
    assert deprecations, "expected at least one DeprecationWarning on reload"
    msg = str(deprecations[0].message)
    assert "legacy" in msg.lower() and "migrate" in msg.lower()
