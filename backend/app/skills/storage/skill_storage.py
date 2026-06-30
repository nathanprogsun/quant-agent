"""SkillStorage abstraction.

Mirrors deer-flow's two-category layout: <root>/public/<name>/SKILL.md and
<root>/custom/<name>/SKILL.md. Concrete backends may swap the filesystem for
a DB or remote store without changing call sites.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from app.skills.types import Skill


class SkillStorage(ABC):
    """Abstract skill storage backend."""

    @abstractmethod
    def load_skills(self) -> list[Skill]:
        """Discover all skills (metadata-only; body not loaded)."""

    @abstractmethod
    def read_body(self, skill: Skill) -> str:
        """Load the SKILL.md body on demand (progressive disclosure)."""

    @abstractmethod
    def update_custom(self, name: str, content: str) -> None:
        """Overwrite a custom skill's SKILL.md, recording the prior body."""

    @abstractmethod
    def read_history(self, name: str) -> list[str]:
        """Return history entries (JSON lines) for a custom skill."""

    @abstractmethod
    def rollback_custom(self, name: str) -> None:
        """Restore the previous body of a custom skill."""

    @staticmethod
    def _skill_md_path(skill: Skill) -> Path:
        """Resolve <container_path>/SKILL.md (no traversal check here)."""
        return Path(skill.container_path) / "SKILL.md"
