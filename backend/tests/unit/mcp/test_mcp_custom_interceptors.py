"""Tests for loading custom MCP interceptors declared in extensions_config.json."""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.tools import BaseTool


def _write(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


@pytest.mark.asyncio
async def test_get_mcp_tools_loads_custom_interceptor(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Custom interceptor declared via ``mcpInterceptors`` is constructed and applied."""

    # Make sure ``ExtensionsConfig.resolve_config_path()`` points at our file.
    cfg_path = _write(
        tmp_path / "extensions_config.json",
        {
            "mcpServers": {
                "live": {"type": "stdio", "command": "echo"},
            },
            "mcpInterceptors": ["app.tests.unit.mcp.fake_interceptor_module:build_it"],
        },
    )

    # A dummy interceptor module. We register it under the test path so
    # ``import_module`` finds it.
    mod = types.ModuleType("app.tests.unit.mcp.fake_interceptor_module")
    called: dict = {"count": 0}

    def _build():
        called["count"] += 1

        async def _interceptor(req, handler):
            return await handler(req)

        return _interceptor

    mod.build_it = _build
    sys.modules["app.tests.unit.mcp.fake_interceptor_module"] = mod
    # Pretend ``app.tests.unit.mcp`` is a package.
    pkg = types.ModuleType("app.tests")
    pkg.__path__ = []  # type: ignore[attr-defined]
    sys.modules["app.tests"] = pkg
    subpkg = types.ModuleType("app.tests.unit")
    subpkg.__path__ = []  # type: ignore[attr-defined]
    sys.modules["app.tests.unit"] = subpkg
    mcppkg = types.ModuleType("app.tests.unit.mcp")
    mcppkg.__path__ = []  # type: ignore[attr-defined]
    sys.modules["app.tests.unit.mcp"] = mcppkg

    # Patch get_settings to point at our temp config.
    class FakeSettings:
        extensions_config_path = str(cfg_path)

    monkeypatch.setattr("app.settings.get_settings", lambda: FakeSettings())

    # Avoid a real MultiServerMCPClient — replace it with a stub that
    # yields one tool per server.
    fake_client_instance = MagicMock()

    async def _get_tools(server_name=None):
        if server_name is None:
            return []
        return [_make_stub_tool(f"{server_name}_ping")]

    fake_client_instance.get_tools = AsyncMock(side_effect=_get_tools)
    monkeypatch.setattr(
        "langchain_mcp_adapters.client.MultiServerMCPClient",
        lambda *args, **kwargs: fake_client_instance,
    )

    from app.mcp.tools import get_mcp_tools  # noqa: PLC0415

    tools = await get_mcp_tools()
    assert called["count"] == 1, "custom interceptor builder should be called once"
    assert len(tools) >= 1


def _make_stub_tool(name: str):
    """Create a fake BaseTool with ``name`` and minimal attrs used by tools.py."""
    tool = MagicMock(spec=BaseTool)
    tool.name = name
    tool.description = ""
    tool.args_schema = None
    tool.metadata = {}
    return tool


def test_interceptor_helper_resolves_string_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """``_resolve_variable('pkg.mod:attr')`` returns the named attribute."""
    mod = types.ModuleType("_resolve_test_mod")
    mod.attr = object()  # sentinel

    sys.modules["_resolve_test_mod"] = mod

    from app.mcp.tools import _resolve_variable  # noqa: PLC0415

    result = _resolve_variable("_resolve_test_mod:attr")
    assert result is mod.attr


def test_interceptor_helper_logs_on_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """Invalid paths log a warning and don't crash the loader."""
    from app.mcp.tools import _resolve_variable  # noqa: PLC0415

    with pytest.raises(ImportError):
        _resolve_variable("not_a_valid_path")
