"""Parse SKILL.md files. Reads YAML frontmatter only; body is on-demand."""

from __future__ import annotations

from pathlib import Path

import yaml

from app.skills.exceptions import SkillParseError, SkillValidationError
from app.skills.types import Skill, SkillCategory

_REQUIRED = ("name", "description")
_BODY_LOAD_DEFAULT = False


def parse_skill_file(
    path: Path,
    category: SkillCategory,
    *,
    load_body: bool = _BODY_LOAD_DEFAULT,
) -> Skill:
    """Parse a SKILL.md file.

    Reads only YAML frontmatter by default. Pass load_body=True to also
    slurp the body (used only by SkillActivationMiddleware for slash
    injection — never by the metadata-only prompt section).
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        raise SkillParseError(f"Cannot read {path}: {e}") from e

    if not text.startswith("---"):
        raise SkillParseError(f"{path}: missing YAML frontmatter delimiter")

    parts = text.split("---", 2)
    if len(parts) < 3:
        raise SkillParseError(f"{path}: unterminated YAML frontmatter")
    fm_raw, body = parts[1], parts[2].lstrip("\n")

    try:
        meta = yaml.safe_load(fm_raw) or {}
    except yaml.YAMLError as e:
        raise SkillParseError(f"{path}: invalid YAML: {e}") from e

    if not isinstance(meta, dict):
        raise SkillParseError(f"{path}: frontmatter must be a mapping")

    missing = [k for k in _REQUIRED if k not in meta]
    if missing:
        raise SkillValidationError(f"{path}: missing required fields: {missing}")

    return Skill(
        name=str(meta["name"]),
        description=str(meta["description"]),
        category=category,
        container_path=str(path.parent),
        license=meta.get("license"),
        allowed_tools=list(meta.get("allowed-tools") or []),
        enabled=True,
        body=body if load_body else None,
    )
