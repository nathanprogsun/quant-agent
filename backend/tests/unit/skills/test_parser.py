"""Tests for SKILL.md frontmatter parser."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.skills.exceptions import SkillParseError, SkillValidationError
from app.skills.parser import parse_skill_file
from app.skills.types import SkillCategory


def _write(tmp: Path, name: str, body: str) -> Path:
    p = tmp / "SKILL.md"
    p.write_text(body, encoding="utf-8")
    return p


def test_parse_minimal_frontmatter(tmp_path: Path) -> None:
    p = _write(tmp_path, "minimal", "---\nname: minimal\ndescription: short\n---\n# Body\n")
    skill = parse_skill_file(p, category=SkillCategory.PUBLIC)
    assert skill.name == "minimal"
    assert skill.description == "short"
    assert skill.container_path == str(tmp_path)


def test_parser_does_not_load_body(tmp_path: Path) -> None:
    p = _write(tmp_path, "x", "---\nname: x\ndescription: y\n---\nHUGE BODY " * 1000)
    skill = parse_skill_file(p, category=SkillCategory.PUBLIC)
    # body is loaded only by explicit read; metadata-only default
    assert skill.body is None or skill.body == ""


def test_invalid_yaml_raises(tmp_path: Path) -> None:
    p = _write(tmp_path, "bad", "---\n: invalid\n---\nbody")
    with pytest.raises(SkillParseError):
        parse_skill_file(p, category=SkillCategory.PUBLIC)


def test_missing_required_field_raises(tmp_path: Path) -> None:
    p = _write(tmp_path, "no_desc", "---\nname: no_desc\n---\nbody")
    with pytest.raises(SkillValidationError):
        parse_skill_file(p, category=SkillCategory.PUBLIC)


def test_allowed_tools_optional(tmp_path: Path) -> None:
    p = _write(
        tmp_path,
        "ok",
        "---\nname: ok\ndescription: d\nallowed-tools:\n  - read_file\n  - bash\n---\nbody",
    )
    skill = parse_skill_file(p, category=SkillCategory.PUBLIC)
    assert skill.allowed_tools == ["read_file", "bash"]


def test_license_optional(tmp_path: Path) -> None:
    p = _write(tmp_path, "lic", "---\nname: lic\ndescription: d\nlicense: MIT\n---\nbody")
    skill = parse_skill_file(p, category=SkillCategory.PUBLIC)
    assert skill.license == "MIT"
