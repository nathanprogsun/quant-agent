"""Tests for ExtensionsConfig MCP-server fields + env-var resolution.

These tests cover the P2 expansion of ``McpServerConfig``:
- ``headers`` for SSE/HTTP transports
- ``oauth`` for OAuth-protected servers
- ``get_enabled_mcp_servers()`` returning the runtime-eligible subset
- ``ExtensionsConfig.resolve_env_variables`` for token resolution
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.config.extensions_config import (
    ExtensionsConfig,
    McpOAuthConfig,
    McpServerConfig,
)


def _write(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_mcp_server_config_accepts_headers_and_oauth() -> None:
    cfg = McpServerConfig.model_validate(
        {
            "type": "http",
            "url": "https://example.com/mcp",
            "headers": {"Authorization": "Bearer token"},
            "oauth": {
                "enabled": True,
                "grant_type": "client_credentials",
                "token_url": "https://example.com/oauth/token",
                "client_id": "id",
                "client_secret": "secret",
            },
        }
    )
    assert cfg.headers == {"Authorization": "Bearer token"}
    assert cfg.oauth is not None
    assert isinstance(cfg.oauth, McpOAuthConfig)
    assert cfg.oauth.grant_type == "client_credentials"


def test_mcp_server_config_transport_alias() -> None:
    """``transport`` is accepted as an alias for ``type`` (deer-flow parity)."""
    cfg = McpServerConfig.model_validate({"transport": "sse", "url": "https://example.com/sse"})
    assert cfg.type == "sse"


def test_get_enabled_mcp_servers_filters_disabled(tmp_path: Path) -> None:
    cfg_path = _write(
        tmp_path / "extensions_config.json",
        {
            "mcpServers": {
                "live": {"type": "stdio", "command": "npx", "enabled": True},
                "off": {"type": "stdio", "command": "npx", "enabled": False},
            }
        },
    )
    cfg = ExtensionsConfig.from_file(cfg_path)
    enabled = cfg.get_enabled_mcp_servers()
    assert "live" in enabled
    assert "off" not in enabled


def test_resolve_env_variables_replaces_strings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MCP_TOKEN", "secret")
    monkeypatch.delenv("MISSING_TOKEN", raising=False)

    raw = {
        "args": ["--token", "$MCP_TOKEN", {"nested": ["$MCP_TOKEN", "$MISSING_TOKEN"]}],
        "env": {"API_KEY": "$MCP_TOKEN"},
    }

    resolved = ExtensionsConfig.resolve_env_variables(raw)

    assert resolved["args"][0] == "--token"
    assert resolved["args"][1] == "secret"
    assert resolved["args"][2]["nested"][0] == "secret"
    assert resolved["args"][2]["nested"][1] == ""
    assert resolved["env"]["API_KEY"] == "secret"


def test_resolve_env_variables_passthrough_non_strings() -> None:
    raw = {"count": 42, "flag": True, "items": [1, 2, 3]}
    assert ExtensionsConfig.resolve_env_variables(raw) == raw


def test_resolve_config_path_returns_settings_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app import settings as settings_mod

    sentinel = "/tmp/quant-agent-extensions.json"
    monkeypatch.setattr(settings_mod, "get_settings", lambda: _FakeSettings(sentinel))
    assert ExtensionsConfig.resolve_config_path() == Path(sentinel)


class _FakeSettings:
    def __init__(self, extensions_config_path: str) -> None:
        self.extensions_config_path = extensions_config_path
