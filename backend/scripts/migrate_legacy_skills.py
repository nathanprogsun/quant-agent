"""Migrate legacy SkillRegistry rows to disk-backed SKILL.md (Task 1.9).

The legacy ``app.core.chat.skills.registry.SkillRegistry`` keeps skill
definitions in memory with an inline ``prompt_template`` body. Plan-1
moves to a disk-backed protocol where each skill lives at
``<skills_root>/custom/<name>/SKILL.md`` with YAML frontmatter (name +
description) and the body loaded on demand.

Run from the ``backend/`` directory::

    uv run python -m scripts.migrate_legacy_skills

The script is idempotent: re-running against the same source registry
produces byte-identical ``SKILL.md`` files and a manifest sidecar.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import yaml

from app.core.chat.skills.registry import SkillRegistry
from app.settings import get_settings
from app.skills.exceptions import SkillParseError, SkillValidationError
from app.skills.parser import parse_skill_file
from app.skills.types import SkillCategory

_MIGRATION_MANIFEST = "_migrated.jsonl"
_CUSTOM_DIR = "custom"
_FRONT_MATTER_DELIM = "---"
_TMP_SUFFIX = ".tmp"


@dataclass(frozen=True)
class MigrationRecord:
    """One row in the migration manifest."""

    name: str
    skill_md_path: str
    migrated: bool
    timestamp: str


@dataclass(frozen=True)
class MigrationReport:
    """Aggregate result of a migration run."""

    records: list[MigrationRecord]
    manifest_path: str | None


def _build_frontmatter(name: str, description: str) -> str:
    """Render the YAML frontmatter block for ``name`` + ``description``.

    Uses ``yaml.safe_dump`` so any future-unsafe strings are quoted.
    Returns the delimiter-wrapped block as a string with a trailing
    newline so concatenation with the body yields a well-formed SKILL.md.
    """
    payload = yaml.safe_dump(
        {"name": name, "description": description},
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
    )
    return f"{_FRONT_MATTER_DELIM}\n{payload}{_FRONT_MATTER_DELIM}\n"


def _write_atomic(path: Path, text: str) -> None:
    """Write ``text`` to ``path`` via a sibling tmp file + atomic replace.

    Avoids partially-written SKILL.md files if the process is killed
    mid-write. On success, no ``.tmp`` sibling remains.
    """
    tmp = path.with_suffix(path.suffix + _TMP_SUFFIX)
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def _migrate_one(
    *,
    name: str,
    description: str,
    body: str,
    skills_root: Path,
) -> MigrationRecord:
    """Write a single SKILL.md atomically and return its manifest row."""
    target_dir = skills_root / _CUSTOM_DIR / name
    target_dir.mkdir(parents=True, exist_ok=True)
    skill_md = target_dir / "SKILL.md"
    text = _build_frontmatter(name=name, description=description) + body
    _write_atomic(skill_md, text)

    # Round-trip self-check: the file MUST be parseable.
    parsed = parse_skill_file(skill_md, category=SkillCategory.CUSTOM, load_body=True)
    if parsed.name != name:
        raise SkillValidationError(
            f"Migration round-trip mismatch: expected {name}, got {parsed.name}"
        )
    if parsed.body != body:
        raise SkillParseError(f"Migration round-trip body mismatch for {name}")

    return MigrationRecord(
        name=name,
        skill_md_path=str(skill_md),
        migrated=True,
        timestamp=datetime.now(tz=UTC).isoformat(),
    )


def migrate_legacy_skills(
    *,
    registry: SkillRegistry | None = None,
    skills_root: Path,
) -> MigrationReport:
    """Migrate every legacy ``SkillRegistry`` row to a ``SKILL.md`` file.

    Args:
        registry: Source registry. ``None`` builds a fresh one (with
            defaults seeded) — the same path the legacy code takes when
            it first imports the module.
        skills_root: Destination directory. The migration writes under
            ``skills_root/custom/<name>/SKILL.md`` for each row, and a
            JSONL manifest at ``skills_root/custom/_migrated.jsonl``.

    Returns:
        A ``MigrationReport`` listing each migrated row and the manifest
        path (or ``None`` if the registry was empty and we never wrote one).
    """
    if registry is None:
        registry = SkillRegistry()

    skills_root = Path(skills_root).resolve()
    skills_root.mkdir(parents=True, exist_ok=True)
    (skills_root / _CUSTOM_DIR).mkdir(parents=True, exist_ok=True)

    records = [
        _migrate_one(
            name=skill.name,
            description=skill.description,
            body=skill.prompt_template,
            skills_root=skills_root,
        )
        for skill in registry.list_all()
    ]

    if not records:
        return MigrationReport(records=[], manifest_path=None)

    manifest = skills_root / _CUSTOM_DIR / _MIGRATION_MANIFEST
    payload = "\n".join(
        json.dumps(
            {
                "name": r.name,
                "skill_md_path": r.skill_md_path,
                "migrated": r.migrated,
                "timestamp": r.timestamp,
            },
            ensure_ascii=False,
        )
        for r in records
    )
    _write_atomic(manifest, payload + "\n")

    return MigrationReport(records=records, manifest_path=str(manifest))


def main() -> int:
    """CLI entry: migrate using settings.skills_root as the destination."""
    settings = get_settings()
    report = migrate_legacy_skills(skills_root=Path(settings.skills_root))
    n = len(report.records)
    print(f"Migrated {n} legacy skill(s).")
    if report.manifest_path:
        print(f"Manifest: {report.manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
