"""Tests for the in-memory MCP tool cache (cache.py)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.mcp import cache as cache_mod


@pytest.fixture(autouse=True)
def _reset_cache() -> None:
    cache_mod._mcp_tools_cache = None
    cache_mod._cache_initialized = False
    cache_mod._config_mtime = None
    yield
    cache_mod._mcp_tools_cache = None
    cache_mod._cache_initialized = False
    cache_mod._config_mtime = None


def _patch_get_mcp_tools(monkeypatch: pytest.MonkeyPatch, tools: list) -> None:
    async def fake() -> list:
        return tools

    monkeypatch.setattr("app.mcp.tools.get_mcp_tools", fake)


def _patch_resolve(monkeypatch: pytest.MonkeyPatch, mtime: float | None) -> None:
    monkeypatch.setattr(cache_mod, "_get_config_mtime", lambda: mtime)


@pytest.mark.asyncio
async def test_initialize_mcp_tools_returns_existing_when_initialized() -> None:
    sentinel = [MagicMock(name="t1"), MagicMock(name="t2")]
    cache_mod._mcp_tools_cache = sentinel
    cache_mod._cache_initialized = True

    tools = await cache_mod.initialize_mcp_tools()
    assert tools is sentinel


@pytest.mark.asyncio
async def test_initialize_mcp_tools_calls_loader_when_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sentinel = [MagicMock(name="only")]

    async def fake() -> list:
        return sentinel

    monkeypatch.setattr("app.mcp.tools.get_mcp_tools", fake)
    _patch_resolve(monkeypatch, None)

    tools = await cache_mod.initialize_mcp_tools()
    assert tools is sentinel


def test_get_cached_mcp_tools_returns_cached_when_initialized() -> None:
    sentinel = [MagicMock(name="x")]
    cache_mod._mcp_tools_cache = sentinel
    cache_mod._cache_initialized = True

    assert cache_mod.get_cached_mcp_tools() is sentinel


def test_get_cached_mcp_tools_returns_empty_when_loader_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def boom() -> list:
        raise RuntimeError("nope")

    monkeypatch.setattr("app.mcp.tools.get_mcp_tools", boom)
    # No event loop, so we hit asyncio.run(). Patch it to raise.
    monkeypatch.setattr("asyncio.run", lambda _coro: (_ for _ in ()).throw(RuntimeError("no loop")))

    result = cache_mod.get_cached_mcp_tools()
    assert result == []


def test_reset_clears_state(monkeypatch: pytest.MonkeyPatch) -> None:
    cache_mod._mcp_tools_cache = [MagicMock(name="x")]
    cache_mod._cache_initialized = True
    cache_mod._config_mtime = 12345.0

    # Avoid hitting session pool real close_all_sync.
    monkeypatch.setattr(
        "app.mcp.session_pool.get_session_pool",
        lambda: type("P", (), {"close_all_sync": lambda self: None})(),
    )
    cache_mod.reset_mcp_tools_cache()
    assert cache_mod._mcp_tools_cache is None
    assert cache_mod._cache_initialized is False
    assert cache_mod._config_mtime is None


def test_cache_stale_when_mtime_increases(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache_mod._cache_initialized = True
    cache_mod._config_mtime = 100.0

    _patch_resolve(monkeypatch, 200.0)
    assert cache_mod._is_cache_stale() is True


def test_cache_not_stale_when_mtime_equal_or_less(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache_mod._cache_initialized = True
    cache_mod._config_mtime = 200.0

    _patch_resolve(monkeypatch, 200.0)
    assert cache_mod._is_cache_stale() is False

    _patch_resolve(monkeypatch, 100.0)
    assert cache_mod._is_cache_stale() is False


def test_cache_not_stale_when_uninitialized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_resolve(monkeypatch, 1.0)
    assert cache_mod._is_cache_stale() is False
