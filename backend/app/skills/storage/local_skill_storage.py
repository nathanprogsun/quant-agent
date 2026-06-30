"""Local filesystem SkillStorage.

Layout:
  <root>/public/<name>/SKILL.md
  <root>/custom/<name>/SKILL.md
  <root>/custom/<name>/.history.jsonl   (append-only edit history)

All read access is confined to <root> via path-traversal checks.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from app.skills.exceptions import SkillNotFoundError, SkillParseError, SkillPathTraversalError
from app.skills.parser import parse_skill_file
from app.skills.storage.skill_storage import SkillStorage
from app.skills.types import Skill, SkillCategory

_SKILL_FILE = "SKILL.md"
_HISTORY_FILE = ".history.jsonl"
_CATEGORY_DIRS = (
    (SkillCategory.PUBLIC, "public"),
    (SkillCategory.CUSTOM, "custom"),
)


class LocalSkillStorage(SkillStorage):
    """Filesystem-backed skill storage rooted at ``root``."""

    def __init__(self, root: Path) -> None:
        self._root: Path = Path(root).resolve()

    # ── discovery ──────────────────────────────────────────────

    def load_skills(self) -> list[Skill]:
        """Discover all skills (metadata-only; body not loaded)."""
        skills: list[Skill] = []
        for category, subdir in _CATEGORY_DIRS:
            base = self._root / subdir
            if not base.is_dir():
                continue
            for entry in sorted(base.iterdir()):
                if not entry.is_dir():
                    continue
                skill_md = entry / _SKILL_FILE
                if not skill_md.exists():
                    continue
                try:
                    skills.append(parse_skill_file(skill_md, category=category))
                except SkillParseError:
                    # Skip malformed skills rather than abort discovery
                    continue
        return skills

    # ── body ───────────────────────────────────────────────────

    def read_body(self, skill: Skill) -> str:
        """Load the SKILL.md body on demand."""
        path = self._safe_skill_md_path(skill)
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as e:
            raise SkillParseError(f"Cannot read {path}: {e}") from e
        if not text.startswith("---"):
            return text
        parts = text.split("---", 2)
        if len(parts) < 3:
            return text
        return parts[2].lstrip("\n")

    # ── custom edit + history ──────────────────────────────────

    def update_custom(self, name: str, content: str) -> None:
        """Overwrite a custom skill's SKILL.md, recording the prior body."""
        skill_md = self._custom_skill_md_path(name)
        if not skill_md.exists():
            raise SkillNotFoundError(f"Custom skill not found: {name}")
        old_body = self._strip_frontmatter_body(skill_md.read_text(encoding="utf-8"))
        self._append_history(
            name, old_body=old_body, new_body=self._strip_frontmatter_body(content)
        )
        skill_md.write_text(content, encoding="utf-8")

    def read_history(self, name: str) -> list[str]:
        """Return history entries (JSON lines) for a custom skill."""
        history_path = self._custom_history_path(name)
        if not history_path.exists():
            # Unknown skill vs. known-but-never-edited: distinguish by dir
            if not (self._root / "custom" / name).is_dir():
                raise SkillNotFoundError(f"Custom skill not found: {name}")
            return []
        return [
            line for line in history_path.read_text(encoding="utf-8").splitlines() if line.strip()
        ]

    def rollback_custom(self, name: str) -> None:
        """Restore the previous body of a custom skill."""
        history_path = self._custom_history_path(name)
        if not history_path.exists():
            raise SkillNotFoundError(f"No history for custom skill: {name}")
        lines = [ln for ln in history_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        if not lines:
            raise SkillNotFoundError(f"Empty history for custom skill: {name}")
        last = json.loads(lines[-1])
        skill_md = self._custom_skill_md_path(name)
        # Rebuild SKILL.md preserving current frontmatter, swapping body
        current = skill_md.read_text(encoding="utf-8") if skill_md.exists() else ""
        frontmatter = self._extract_frontmatter(current)
        skill_md.write_text(f"{frontmatter}{last['old_body']}", encoding="utf-8")
        # Drop the rolled-back entry
        remaining = lines[:-1]
        history_path.write_text(
            ("\n".join(remaining) + "\n") if remaining else "", encoding="utf-8"
        )

    # ── path safety ────────────────────────────────────────────

    def _safe_skill_md_path(self, skill: Skill) -> Path:
        """Resolve <container_path>/SKILL.md, rejecting traversal outside root."""
        candidate = (Path(skill.container_path) / _SKILL_FILE).resolve()
        try:
            candidate.relative_to(self._root)
        except ValueError as e:
            raise SkillPathTraversalError(
                f"Refusing to read outside storage root: {candidate}"
            ) from e
        return candidate

    def _custom_skill_md_path(self, name: str) -> Path:
        return self._root / "custom" / name / _SKILL_FILE

    def _custom_history_path(self, name: str) -> Path:
        return self._root / "custom" / name / _HISTORY_FILE

    # ── helpers ────────────────────────────────────────────────

    def _append_history(self, name: str, *, old_body: str, new_body: str) -> None:
        history_path = self._custom_history_path(name)
        history_path.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "timestamp": datetime.now(tz=UTC).isoformat(),
            "old_body": old_body,
            "new_body": new_body,
        }
        with history_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")

    @staticmethod
    def _strip_frontmatter_body(text: str) -> str:
        if not text.startswith("---"):
            return text
        parts = text.split("---", 2)
        if len(parts) < 3:
            return text
        return parts[2].lstrip("\n")

    @staticmethod
    def _extract_frontmatter(text: str) -> str:
        """Return the leading YAML frontmatter block (delimiters included)."""
        if not text.startswith("---"):
            return ""
        parts = text.split("---", 2)
        if len(parts) < 3:
            return text
        return f"---{parts[1]}---\n"
