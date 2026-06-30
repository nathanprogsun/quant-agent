"""Skills toggle service — orchestrates storage + config + cache invalidation.

Bridges the disk-based skill storage (LocalSkillStorage) with the runtime
toggle state (ExtensionsConfig) and the LRU prompt-section cache. The REST
toggle API (P1.5) calls ``set_enabled`` to persist a toggle and invalidate
the cached prompt section so the next agent turn reflects the new state.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.config.extensions_config import ExtensionsConfig
from app.core.chat.agent.skills_prompt import _invalidate_skills_cache
from app.settings import get_settings
from app.skills.exceptions import SkillNotFoundError
from app.skills.storage.local_skill_storage import LocalSkillStorage


@dataclass(frozen=True)
class SkillMetadata:
    """Metadata-only skill view returned by the REST API."""

    name: str
    description: str
    category: str
    container_path: str
    enabled: bool


class SkillsService:
    """Orchestrates skill discovery, toggle state, and cache invalidation."""

    def __init__(self, storage: LocalSkillStorage, config_path: str | Path) -> None:
        self._storage = storage
        self._config_path = Path(config_path)

    # ── read ───────────────────────────────────────────────────

    def list_skills(self) -> list[SkillMetadata]:
        """Return all discovered skills with their runtime enabled state."""
        config = self._load_config()
        return [
            SkillMetadata(
                name=skill.name,
                description=skill.description,
                category=skill.category.value,
                container_path=skill.container_path,
                enabled=config.is_skill_enabled(skill.name),
            )
            for skill in self._storage.load_skills()
        ]

    # ── write ──────────────────────────────────────────────────

    def set_enabled(self, name: str, *, enabled: bool) -> SkillMetadata:
        """Toggle a skill's enabled state, persist, and invalidate cache.

        Raises:
            SkillNotFoundError: if the skill is not present on disk.
        """
        skills = {s.name: s for s in self._storage.load_skills()}
        if name not in skills:
            raise SkillNotFoundError(f"Skill not found: {name}")
        config = self._load_config()
        config.set_skill_enabled(name, enabled=enabled, path=self._config_path)
        _invalidate_skills_cache()
        skill = skills[name]
        return SkillMetadata(
            name=skill.name,
            description=skill.description,
            category=skill.category.value,
            container_path=skill.container_path,
            enabled=enabled,
        )

    # ── helpers ────────────────────────────────────────────────

    def _load_config(self) -> ExtensionsConfig:
        """Load (or create) the extensions config from disk."""
        if not self._config_path.exists():
            self._config_path.parent.mkdir(parents=True, exist_ok=True)
            self._config_path.write_text('{"skills": {}}\n', encoding="utf-8")
        return ExtensionsConfig.from_file(self._config_path)


def make_skills_service_from_settings() -> SkillsService:
    """Build a SkillsService from application settings."""
    settings = get_settings()
    storage = LocalSkillStorage(root=Path(settings.skills_root))
    return SkillsService(storage=storage, config_path=Path(settings.extensions_config_path))
