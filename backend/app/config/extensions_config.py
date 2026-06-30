"""extensions_config.json schema + Pydantic loader.

Runtime-toggleable state (skills, MCP servers, interceptors) lives in
``extensions_config.json``; boot-time config (model, paths) lives in
``app/settings.py``. Both load via ``ExtensionsConfig.from_file()``.

Mirrors deer-flow's extensions_config model (adapted to Pydantic v2).
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field, PrivateAttr


class SkillStateConfig(BaseModel):
    """Per-skill runtime toggle state."""

    enabled: bool = True


class McpServerConfig(BaseModel):
    """MCP server registration (consumed by P2)."""

    # Transport-specific fields are intentionally permissive; P2 tightens them.
    type: str = "stdio"
    command: str | None = None
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    url: str | None = None
    enabled: bool = True


class McpInterceptorsConfig(BaseModel):
    """Custom MCP interceptor registration (consumed by P2)."""

    module: str
    enabled: bool = True


class ExtensionsConfig(BaseModel):
    """Root extensions config: skills + MCP servers + interceptors."""

    skills: dict[str, SkillStateConfig] = Field(default_factory=dict)
    mcp_servers: dict[str, McpServerConfig] = Field(alias="mcpServers", default_factory=dict)
    mcp_interceptors: list[McpInterceptorsConfig] = Field(
        alias="mcpInterceptors", default_factory=list
    )

    model_config = {"populate_by_name": True}

    _source_path: Path | None = PrivateAttr(default=None)

    # ── load / persist ─────────────────────────────────────────

    @classmethod
    def from_file(cls, path: str | Path) -> ExtensionsConfig:
        """Load config from a JSON file on disk."""
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"Extensions config not found: {p}")
        data = json.loads(p.read_text(encoding="utf-8"))
        cfg = cls.model_validate(data)
        cfg._source_path = p
        return cfg

    def save(self, path: str | Path) -> None:
        """Persist config to disk atomically (write+replace)."""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        payload = self.model_dump(by_alias=True, exclude_none=True)
        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        tmp.replace(p)

    # ── skill toggle helpers ───────────────────────────────────

    def is_skill_enabled(self, name: str) -> bool:
        """Unknown skills default to enabled (opt-out toggle)."""
        entry = self.skills.get(name)
        if entry is None:
            return True
        return entry.enabled

    def set_skill_enabled(
        self, name: str, *, enabled: bool, path: str | Path | None = None
    ) -> None:
        """Update skill toggle in-memory and (optionally) persist to disk.

        Defaults to the file this config was loaded from.
        """
        self.skills[name] = SkillStateConfig(enabled=enabled)
        target = path if path is not None else self._source_path
        if target is not None:
            self.save(target)
