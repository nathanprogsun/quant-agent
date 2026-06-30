"""extensions_config.json schema + Pydantic loader.

Runtime-toggleable state (skills, MCP servers, interceptors) lives in
``extensions_config.json``; boot-time config (model, paths) lives in
``app/settings.py``. Both load via ``ExtensionsConfig.from_file()``.

Mirrors deer-flow's extensions_config model (adapted to Pydantic v2). P2.2
extends ``McpServerConfig`` with ``headers``, ``oauth``, and an alias
``transport``; adds ``get_enabled_mcp_servers`` and
``resolve_env_variables`` (deer-flow parity for secret interpolation).
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from pydantic import AliasChoices, BaseModel, Field, PrivateAttr, field_validator

# Module-level so pydantic does not turn it into a ModelPrivateAttr on the
# BaseModel. Matches both ``$VAR`` and ``${VAR}`` (deer-flow parity); a missing
# variable expands to "" so a partially-configured operator env does not crash.
_ENV_VAR_RE = re.compile(r"\$\{([A-Z_][A-Z0-9_]*)\}|(?<!\\)\$([A-Z_][A-Z0-9_]*)")


class SkillStateConfig(BaseModel):
    """Per-skill runtime toggle state."""

    enabled: bool = True


class McpOAuthConfig(BaseModel):
    """OAuth token acquisition config for MCP servers (deer-flow parity)."""

    enabled: bool = False
    grant_type: str = "client_credentials"
    token_url: str
    client_id: str | None = None
    client_secret: str | None = None
    refresh_token: str | None = None
    scope: str | None = None
    audience: str | None = None
    extra_token_params: dict[str, str] = Field(default_factory=dict)
    token_field: str = "access_token"
    token_type_field: str = "token_type"
    expires_in_field: str = "expires_in"
    default_token_type: str = "Bearer"
    refresh_skew_seconds: int = 30


class McpServerConfig(BaseModel):
    """MCP server registration consumed by app.mcp.

    ``type`` defaults to ``stdio``; the alternate name ``transport`` is
    accepted as a Pydantic alias so ``extensions_config.json`` written in
    the MCP-spec style (``transport: sse``) loads without rewriting.
    """

    # Pydantic accepts both ``type`` and ``transport`` (alias).
    type: str = Field(default="stdio", validation_alias=AliasChoices("type", "transport"))
    command: str | None = None
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    url: str | None = None
    headers: dict[str, str] = Field(default_factory=dict)
    enabled: bool = True
    oauth: McpOAuthConfig | None = None

    model_config = {"populate_by_name": True}


class McpInterceptorsConfig(BaseModel):
    """Custom MCP interceptor registration (consumed by P2).

    Either a string ``"pkg.module:builder_callable"`` (deer-flow style)
    or a structured entry with ``module`` + ``enabled`` flag.
    """

    module: str
    enabled: bool = True

    @classmethod
    def coerce(cls, raw: object) -> McpInterceptorsConfig | None:
        """Best-effort coercion from a JSON value to the schema model."""
        if isinstance(raw, cls):
            return raw
        if isinstance(raw, str):
            return cls(module=raw, enabled=True)
        return None


def _coerce_interceptors(value: object) -> list[McpInterceptorsConfig]:
    if value is None:
        return []
    if isinstance(value, list):
        return [c for c in (McpInterceptorsConfig.coerce(v) for v in value) if c is not None]
    coerced = McpInterceptorsConfig.coerce(value)
    return [coerced] if coerced is not None else []


class ExtensionsConfig(BaseModel):
    """Root extensions config: skills + MCP servers + interceptors."""

    skills: dict[str, SkillStateConfig] = Field(default_factory=dict)
    mcp_servers: dict[str, McpServerConfig] = Field(alias="mcpServers", default_factory=dict)
    mcp_interceptors: list[McpInterceptorsConfig] = Field(
        alias="mcpInterceptors",
        default_factory=list,
        # ``McpInterceptorsConfig.coerce`` handles both strings and dicts; without a
        # custom validator Pydantic rejects the loose string form used by
        # deer-flow's ``"pkg.module:builder"`` shorthand.
        json_schema_extra={"deer_flow_string_or_struct": True},
    )

    @field_validator("mcp_interceptors", mode="before")
    @classmethod
    def _validate_interceptors(cls, value):  # type: ignore[no-untyped-def]
        return _coerce_interceptors(value)

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

    # ── MCP server helpers ─────────────────────────────────────

    def get_enabled_mcp_servers(self) -> dict[str, McpServerConfig]:
        """Return the subset of servers with ``enabled=True``.

        Filters at the model level; transport-specific validation happens
        downstream in ``app.mcp.client.build_server_params``.
        """
        return {name: cfg for name, cfg in self.mcp_servers.items() if cfg.enabled}

    # ── env-var resolution ─────────────────────────────────────

    @classmethod
    def resolve_env_variables(cls, value: object) -> object:
        """Recursively expand ``$VAR`` / ``${VAR}`` from the process environment.

        Mirrors deer-flow's behaviour: missing variables expand to empty string
        rather than raising, so a partially-configured operator setup does not
        crash every load. Non-string scalars are returned unchanged.
        """
        if isinstance(value, str):
            return _ENV_VAR_RE.sub(lambda m: os.environ.get(m.group(1) or m.group(2), ""), value)
        if isinstance(value, dict):
            return {k: cls.resolve_env_variables(v) for k, v in value.items()}
        if isinstance(value, list):
            return [cls.resolve_env_variables(v) for v in value]
        if isinstance(value, tuple):
            return tuple(cls.resolve_env_variables(v) for v in value)
        return value

    # ── config path resolution ─────────────────────────────────

    @classmethod
    def resolve_config_path(cls) -> Path | None:
        """Return the on-disk path to ``extensions_config.json``.

        Reads ``Settings.extensions_config_path`` (cached). Returns
        ``None`` when the setting is empty/missing so callers can decide
        between default-init and skip.
        """
        from app.settings import get_settings

        try:
            cfg_path = get_settings().extensions_config_path
        except Exception:
            return None
        if not cfg_path:
            return None
        return Path(cfg_path)


# Module-level re-export marker: ``AliasChoices`` is imported at the top of
# the file and used on ``McpServerConfig.type``; downstream tooling that
# flags "unused import" for module-level pydantic types is silenced by the
# trailing reference below.
_ = AliasChoices
