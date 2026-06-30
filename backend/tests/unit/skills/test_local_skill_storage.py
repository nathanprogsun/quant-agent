"""Tests for LocalSkillStorage: discovery and history."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from app.skills.exceptions import SkillNotFoundError, SkillPathTraversalError
from app.skills.storage.local_skill_storage import LocalSkillStorage
from app.skills.types import SkillCategory


def _make_skill_dir(root: Path, category: str, name: str, body: str = "body") -> None:
    d = root / category / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: desc for {name}\n---\n{body}",
        encoding="utf-8",
    )


def test_load_skills_discovers_public_and_custom(tmp_path: Path) -> None:
    _make_skill_dir(tmp_path, "public", "deep-research")
    _make_skill_dir(tmp_path, "custom", "user-skill")
    storage = LocalSkillStorage(root=tmp_path)
    skills = storage.load_skills()
    names = {s.name for s in skills}
    assert names == {"deep-research", "user-skill"}


def test_load_skills_assigns_category(tmp_path: Path) -> None:
    _make_skill_dir(tmp_path, "public", "a")
    _make_skill_dir(tmp_path, "custom", "b")
    storage = LocalSkillStorage(root=tmp_path)
    by_name = {s.name: s for s in storage.load_skills()}
    assert by_name["a"].category == SkillCategory.PUBLIC
    assert by_name["b"].category == SkillCategory.CUSTOM


def test_load_skills_skips_dirs_without_skill_md(tmp_path: Path) -> None:
    _make_skill_dir(tmp_path, "public", "ok")
    (tmp_path / "public" / "broken").mkdir(parents=True)
    storage = LocalSkillStorage(root=tmp_path)
    names = {s.name for s in storage.load_skills()}
    assert names == {"ok"}


def test_read_body_loads_on_demand(tmp_path: Path) -> None:
    _make_skill_dir(tmp_path, "custom", "x", body="the body text")
    storage = LocalSkillStorage(root=tmp_path)
    skills = storage.load_skills()
    skill = next(s for s in skills if s.name == "x")
    assert skill.body in (None, "")
    body = storage.read_body(skill)
    assert body == "the body text"


def test_update_custom_creates_history_entry(tmp_path: Path) -> None:
    _make_skill_dir(tmp_path, "custom", "x", body="v1")
    storage = LocalSkillStorage(root=tmp_path)
    storage.update_custom("x", "---\nname: x\ndescription: d\n---\nv2")
    history = storage.read_history("x")
    assert len(history) == 1
    entry = json.loads(history[0]) if isinstance(history[0], str) else history[0]
    assert entry["old_body"] == "v1"


def test_update_custom_overwrites_current_body(tmp_path: Path) -> None:
    _make_skill_dir(tmp_path, "custom", "x", body="v1")
    storage = LocalSkillStorage(root=tmp_path)
    storage.update_custom("x", "---\nname: x\ndescription: d\n---\nv2")
    skill = next(s for s in storage.load_skills() if s.name == "x")
    assert storage.read_body(skill) == "v2"


def test_read_history_empty_when_no_edits(tmp_path: Path) -> None:
    _make_skill_dir(tmp_path, "custom", "x")
    storage = LocalSkillStorage(root=tmp_path)
    assert storage.read_history("x") == []


def test_rollback_custom_restores_previous_body(tmp_path: Path) -> None:
    _make_skill_dir(tmp_path, "custom", "x", body="v1")
    storage = LocalSkillStorage(root=tmp_path)
    storage.update_custom("x", "---\nname: x\ndescription: d\n---\nv2")
    storage.rollback_custom("x")
    skill = next(s for s in storage.load_skills() if s.name == "x")
    assert storage.read_body(skill) == "v1"


def test_read_body_rejects_path_traversal(tmp_path: Path) -> None:
    _make_skill_dir(tmp_path, "custom", "x", body="ok")
    storage = LocalSkillStorage(root=tmp_path)
    malicious = replace(
        next(s for s in storage.load_skills() if s.name == "x"),
        container_path=str(tmp_path.parent),  # outside storage root
    )
    with pytest.raises(SkillPathTraversalError):
        storage.read_body(malicious)


def test_read_body_rejects_traversal_via_skill_name(tmp_path: Path) -> None:
    _make_skill_dir(tmp_path, "custom", "x", body="ok")
    storage = LocalSkillStorage(root=tmp_path)
    base = next(s for s in storage.load_skills() if s.name == "x")
    # A malicious caller crafts a container_path whose SKILL.md escapes root
    malicious = replace(base, container_path=str(tmp_path / "custom" / ".." / ".."))
    with pytest.raises(SkillPathTraversalError):
        storage.read_body(malicious)


def test_update_custom_unknown_raises(tmp_path: Path) -> None:
    storage = LocalSkillStorage(root=tmp_path)
    with pytest.raises(SkillNotFoundError):
        storage.update_custom("nope", "---\nname: nope\ndescription: d\n---\nbody")


def test_read_history_unknown_raises(tmp_path: Path) -> None:
    storage = LocalSkillStorage(root=tmp_path)
    with pytest.raises((SkillNotFoundError, SkillPathTraversalError)):
        storage.read_history("nope")
