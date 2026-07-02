"""Tests for ``MCPSessionPool`` LRU eviction, looping semantics, and scope/server close."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.mcp.session_pool import MCPSessionPool, get_session_pool, reset_session_pool


@pytest.fixture(autouse=True)
def _reset_pool() -> None:
    reset_session_pool()
    yield
    reset_session_pool()


def _stub_create_session(monkeypatch: pytest.MonkeyPatch) -> tuple[MagicMock, MagicMock]:
    """Replace ``langchain_mcp_adapters.sessions.create_session`` with stubs.

    ``create_session`` returns a *fresh* context manager per call so each
    pool entry sees a distinct session object.
    """

    def _factory(_connection: dict) -> MagicMock:
        fake_cm = MagicMock()
        fake_session = MagicMock()
        fake_session.initialize = AsyncMock(return_value=None)
        fake_cm.__aenter__ = AsyncMock(return_value=fake_session)
        fake_cm.__aexit__ = AsyncMock(return_value=None)
        return fake_cm

    create_session = MagicMock(side_effect=_factory)

    import app.mcp.session_pool as pool_mod  # noqa: PLC0415

    monkeypatch.setattr(pool_mod, "create_session", create_session, raising=False)
    import langchain_mcp_adapters.sessions as sessions_mod  # noqa: PLC0415

    monkeypatch.setattr(sessions_mod, "create_session", create_session, raising=False)
    return create_session, _factory


@pytest.mark.asyncio
async def test_get_session_creates_one_entry(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_create_session(monkeypatch)

    pool = MCPSessionPool()
    sess = await pool.get_session("srv", "scope-a", {"x": 1})
    assert sess is not None
    assert len(pool._entries) == 1
    await pool.close_all()


@pytest.mark.asyncio
async def test_get_session_returns_cached_for_same_key(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_create_session(monkeypatch)

    pool = MCPSessionPool()
    sess1 = await pool.get_session("srv", "scope-a", {"x": 1})
    sess2 = await pool.get_session("srv", "scope-a", {"x": 1})
    assert sess1 is sess2
    assert len(pool._entries) == 1
    await pool.close_all()


@pytest.mark.asyncio
async def test_get_session_distinct_scopes(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_create_session(monkeypatch)

    pool = MCPSessionPool()
    sess_a = await pool.get_session("srv", "scope-a", {"x": 1})
    sess_b = await pool.get_session("srv", "scope-b", {"x": 1})
    assert sess_a is not sess_b
    assert len(pool._entries) == 2
    await pool.close_all()


@pytest.mark.asyncio
async def test_lru_eviction_at_capacity(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_create_session(monkeypatch)

    pool = MCPSessionPool()
    pool.MAX_SESSIONS = 3
    for i in range(3):
        await pool.get_session("srv", f"scope-{i}", {"x": i})
    # Touch scope-0 to bump it to the most-recently-used.
    await pool.get_session("srv", "scope-0", {"x": 0})
    # Insert one more — oldest (scope-1) should be evicted.
    await pool.get_session("srv", "scope-new", {"x": 99})

    keys = list(pool._entries.keys())
    assert ("srv", "scope-1") not in keys
    assert ("srv", "scope-new") in keys
    await pool.close_all()


@pytest.mark.asyncio
async def test_close_scope_drops_only_matching(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_create_session(monkeypatch)

    pool = MCPSessionPool()
    await pool.get_session("srv", "scope-a", {})
    await pool.get_session("srv", "scope-b", {})
    await pool.close_scope("scope-a")

    keys = list(pool._entries.keys())
    assert ("srv", "scope-a") not in keys
    assert ("srv", "scope-b") in keys
    await pool.close_all()


@pytest.mark.asyncio
async def test_close_server_drops_only_matching(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_create_session(monkeypatch)

    pool = MCPSessionPool()
    await pool.get_session("srv-a", "scope", {})
    await pool.get_session("srv-b", "scope", {})
    await pool.close_server("srv-a")

    keys = list(pool._entries.keys())
    assert ("srv-a", "scope") not in keys
    assert ("srv-b", "scope") in keys
    await pool.close_all()


def test_module_level_singleton_is_stable() -> None:
    p1 = get_session_pool()
    p2 = get_session_pool()
    assert p1 is p2
    reset_session_pool()
    p3 = get_session_pool()
    assert p1 is not p3
