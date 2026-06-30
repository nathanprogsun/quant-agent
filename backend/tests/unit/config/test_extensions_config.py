"""Tests for ExtensionsConfig + SkillStateConfig loader."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.config.extensions_config import ExtensionsConfig, SkillStateConfig


def _write(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_from_file_loads_skill_state(tmp_path: Path) -> None:
    cfg_path = _write(
        tmp_path / "extensions_config.json",
        {"skills": {"deep-research": {"enabled": True}, "user-skill": {"enabled": False}}},
    )
    cfg = ExtensionsConfig.from_file(cfg_path)
    assert isinstance(cfg.skills["deep-research"], SkillStateConfig)
    assert cfg.is_skill_enabled("deep-research") is True
    assert cfg.is_skill_enabled("user-skill") is False


def test_is_skill_enabled_unknown_defaults_true(tmp_path: Path) -> None:
    cfg_path = _write(tmp_path / "extensions_config.json", {"skills": {}})
    cfg = ExtensionsConfig.from_file(cfg_path)
    # Unknown skill defaults to enabled (opt-out toggle)
    assert cfg.is_skill_enabled("unknown") is True


def test_reload_picks_up_changes(tmp_path: Path) -> None:
    cfg_path = _write(
        tmp_path / "extensions_config.json",
        {"skills": {"x": {"enabled": True}}},
    )
    cfg = ExtensionsConfig.from_file(cfg_path)
    assert cfg.is_skill_enabled("x") is True
    # Rewrite file with x disabled
    _write(tmp_path / "extensions_config.json", {"skills": {"x": {"enabled": False}}})
    reloaded = ExtensionsConfig.from_file(cfg_path)
    assert reloaded.is_skill_enabled("x") is False


def test_set_skill_enabled_writes_back(tmp_path: Path) -> None:
    cfg_path = _write(tmp_path / "extensions_config.json", {"skills": {"x": {"enabled": True}}})
    cfg = ExtensionsConfig.from_file(cfg_path)
    cfg.set_skill_enabled("x", enabled=False)
    # In-memory state updated
    assert cfg.is_skill_enabled("x") is False
    # Persisted to disk
    on_disk = json.loads(cfg_path.read_text(encoding="utf-8"))
    assert on_disk["skills"]["x"]["enabled"] is False


def test_set_skill_enabled_for_new_skill_creates_entry(tmp_path: Path) -> None:
    cfg_path = _write(tmp_path / "extensions_config.json", {"skills": {}})
    cfg = ExtensionsConfig.from_file(cfg_path)
    cfg.set_skill_enabled("brand-new", enabled=False)
    on_disk = json.loads(cfg_path.read_text(encoding="utf-8"))
    assert on_disk["skills"]["brand-new"]["enabled"] is False


def test_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        ExtensionsConfig.from_file(tmp_path / "nope.json")


def test_mcp_servers_and_interceptors_optional(tmp_path: Path) -> None:
    cfg_path = _write(tmp_path / "extensions_config.json", {"skills": {}})
    cfg = ExtensionsConfig.from_file(cfg_path)
    assert cfg.mcp_servers == {}
    assert cfg.mcp_interceptors == []
