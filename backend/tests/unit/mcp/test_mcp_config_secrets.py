"""Tests for env-var secret resolution in extensions_config.json (deer-flow parity).

The loader does NOT auto-resolve env vars at ``from_file`` time — the raw
``$TOKEN`` strings round-trip faithfully. ``ExtensionsConfig.resolve_env_variables``
is the public helper callers (e.g. ``app.mcp.client.build_server_params``)
must invoke to interpolate secrets before handing params to the client.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.config.extensions_config import ExtensionsConfig
from app.mcp.client import build_server_params


def _write(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_loader_round_trips_raw_token_strings(tmp_path: Path) -> None:
    cfg_path = _write(
        tmp_path / "extensions_config.json",
        {
            "mcpServers": {
                "fs": {
                    "type": "stdio",
                    "command": "npx",
                    "args": ["--token", "$MY_TOKEN"],
                    "env": {"API_KEY": "$MY_TOKEN"},
                }
            }
        },
    )
    cfg = ExtensionsConfig.from_file(cfg_path)
    fs = cfg.mcp_servers["fs"]
    assert fs.args[-1] == "$MY_TOKEN"
    assert fs.env["API_KEY"] == "$MY_TOKEN"


def test_build_server_params_resolves_env_vars_before_client(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """``build_server_params`` invokes ``resolve_env_variables`` automatically."""

    monkeypatch.setenv("MY_TOKEN", "abc123")
    cfg_path = _write(
        tmp_path / "extensions_config.json",
        {
            "mcpServers": {
                "fs": {
                    "type": "stdio",
                    "command": "npx",
                    "args": ["--token", "$MY_TOKEN"],
                    "env": {"API_KEY": "$MY_TOKEN"},
                }
            }
        },
    )
    cfg = ExtensionsConfig.from_file(cfg_path)
    fs = cfg.mcp_servers["fs"]

    # Without resolution, raw $MY_TOKEN stays:
    raw_params = build_server_params("fs", fs, resolve_secrets=False)
    assert "--token" in raw_params["args"]
    assert raw_params["args"][1] == "$MY_TOKEN"
    assert raw_params["env"]["API_KEY"] == "$MY_TOKEN"

    # With resolution, secret interpolates:
    resolved_params = build_server_params("fs", fs, resolve_secrets=True)
    assert resolved_params["args"][1] == "abc123"
    assert resolved_params["env"]["API_KEY"] == "abc123"


def test_env_var_braced_form(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MY_TOKEN", "braced")
    raw = {"X": "${MY_TOKEN}"}
    assert ExtensionsConfig.resolve_env_variables(raw) == {"X": "braced"}


def test_missing_env_var_expands_to_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DEFINITELY_NOT_SET", raising=False)
    raw = {"X": "$DEFINITELY_NOT_SET"}
    assert ExtensionsConfig.resolve_env_variables(raw) == {"X": ""}


def test_runtime_resolve_env_variables_helper(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("X", "expanded")
    raw = {"a": "$X", "b": [{"inner": "$X"}], "n": 1, "flag": True}
    resolved = ExtensionsConfig.resolve_env_variables(raw)
    assert resolved["a"] == "expanded"
    assert resolved["b"][0]["inner"] == "expanded"
    assert resolved["n"] == 1
    assert resolved["flag"] is True
