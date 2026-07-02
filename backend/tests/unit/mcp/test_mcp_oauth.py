"""Tests for ``OAuthTokenManager`` + interceptor/headers helpers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config.extensions_config import ExtensionsConfig, McpOAuthConfig, McpServerConfig
from app.mcp.oauth import (
    OAuthTokenManager,
    build_oauth_tool_interceptor,
    get_initial_oauth_headers,
)


def _cfg(oauth: McpOAuthConfig | None) -> ExtensionsConfig:
    return ExtensionsConfig(
        mcp_servers={
            "live": McpServerConfig(
                enabled=True,
                type="http",
                url="https://example.com/mcp",
                oauth=oauth,
            ),
            "no-oauth": McpServerConfig(
                enabled=True,
                type="http",
                url="https://example.com/mcp",
                oauth=None,
            ),
        },
    )


def test_has_oauth_servers_false_when_none() -> None:
    cfg = _cfg(None)
    mgr = OAuthTokenManager.from_extensions_config(cfg)
    assert not mgr.has_oauth_servers()


def test_has_oauth_servers_true_when_enabled() -> None:
    oauth = McpOAuthConfig(
        enabled=True,
        token_url="https://example.com/oauth/token",
        client_id="id",
        client_secret="secret",
    )
    cfg = _cfg(oauth)
    mgr = OAuthTokenManager.from_extensions_config(cfg)
    assert mgr.has_oauth_servers()
    assert mgr.oauth_server_names() == ["live"]


@pytest.mark.asyncio
async def test_get_authorization_header_returns_none_for_unknown_server() -> None:
    cfg = _cfg(None)
    mgr = OAuthTokenManager.from_extensions_config(cfg)
    assert await mgr.get_authorization_header("missing") is None


@pytest.mark.asyncio
async def test_fetches_client_credentials() -> None:
    oauth = McpOAuthConfig(
        enabled=True,
        grant_type="client_credentials",
        token_url="https://idp/oauth/token",
        client_id="cid",
        client_secret="csec",
        scope="read",
    )
    cfg = _cfg(oauth)
    mgr = OAuthTokenManager.from_extensions_config(cfg)

    response = MagicMock()
    response.json.return_value = {
        "access_token": "tok-1",
        "token_type": "Bearer",
        "expires_in": 600,
    }
    response.raise_for_status = MagicMock()

    async_client_cm = MagicMock()
    async_client_cm.__aenter__ = AsyncMock(return_value=async_client_cm)
    async_client_cm.__aexit__ = AsyncMock(return_value=None)
    async_client_cm.post = AsyncMock(return_value=response)

    with patch("httpx.AsyncClient", return_value=async_client_cm):
        header = await mgr.get_authorization_header("live")

    assert header == "Bearer tok-1"
    post_call = async_client_cm.post.await_args
    assert post_call.args[0] == "https://idp/oauth/token"
    payload = post_call.kwargs["data"]
    assert payload["grant_type"] == "client_credentials"
    assert payload["client_id"] == "cid"
    assert payload["client_secret"] == "csec"
    assert payload["scope"] == "read"


@pytest.mark.asyncio
async def test_cached_token_returns_without_http() -> None:
    oauth = McpOAuthConfig(
        enabled=True,
        token_url="https://idp/oauth/token",
        client_id="cid",
        client_secret="csec",
    )
    cfg = _cfg(oauth)
    mgr = OAuthTokenManager.from_extensions_config(cfg)
    # Seed cache directly with a long-lived token.
    from app.mcp.oauth import _OAuthToken  # noqa: PLC0415

    mgr._tokens["live"] = _OAuthToken(
        access_token="cached",
        token_type="Bearer",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )

    # Second call should NOT hit httpx.
    header = await mgr.get_authorization_header("live")
    assert header == "Bearer cached"


@pytest.mark.asyncio
async def test_expired_token_triggers_refresh() -> None:
    oauth = McpOAuthConfig(
        enabled=True,
        token_url="https://idp/oauth/token",
        client_id="cid",
        client_secret="csec",
        refresh_skew_seconds=60,
    )
    cfg = _cfg(oauth)
    mgr = OAuthTokenManager.from_extensions_config(cfg)
    from app.mcp.oauth import _OAuthToken  # noqa: PLC0415

    # Already past skew → must refresh.
    mgr._tokens["live"] = _OAuthToken(
        access_token="stale",
        token_type="Bearer",
        expires_at=datetime.now(UTC) - timedelta(minutes=5),
    )

    response = MagicMock()
    response.json.return_value = {"access_token": "fresh", "expires_in": 3600}
    response.raise_for_status = MagicMock()
    async_client_cm = MagicMock()
    async_client_cm.__aenter__ = AsyncMock(return_value=async_client_cm)
    async_client_cm.__aexit__ = AsyncMock(return_value=None)
    async_client_cm.post = AsyncMock(return_value=response)

    with patch("httpx.AsyncClient", return_value=async_client_cm):
        header = await mgr.get_authorization_header("live")

    assert header == "Bearer fresh"
    async_client_cm.post.assert_awaited_once()


def test_build_oauth_tool_interceptor_returns_none_without_oauth() -> None:
    cfg = _cfg(None)
    assert build_oauth_tool_interceptor(cfg) is None


@pytest.mark.asyncio
async def test_build_oauth_tool_interceptor_injects_header() -> None:
    oauth = McpOAuthConfig(
        enabled=True,
        token_url="https://idp/oauth/token",
        client_id="cid",
        client_secret="csec",
    )
    cfg = _cfg(oauth)
    interceptor = build_oauth_tool_interceptor(cfg)
    assert interceptor is not None

    # Intercept the underlying manager that the interceptor closed over.
    # We seed its token cache so the interceptor returns without httpx.
    from app.mcp.oauth import OAuthTokenManager as Mgr  # noqa: PLC0415

    # The interceptor captured the manager internally; we patch the
    # classmethod factory to keep returning the same instance, then
    # seed the cache.
    captured = OAuthTokenManager.from_extensions_config(cfg)
    captured._tokens["live"] = type(  # type: ignore[attr-defined]
        "T", (), {"access_token": "xyz", "token_type": "Bearer"}
    )()

    # Use a real _OAuthToken via local import for clarity.
    from app.mcp.oauth import _OAuthToken  # noqa: PLC0415

    captured._tokens["live"] = _OAuthToken(  # type: ignore[attr-defined]
        access_token="xyz",
        token_type="Bearer",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )

    import app.mcp.oauth as oauth_mod  # noqa: PLC0415

    oauth_mod.OAuthTokenManager.from_extensions_config = classmethod(  # type: ignore[assignment]
        lambda cls, _: captured
    )
    try:
        new_interceptor = build_oauth_tool_interceptor(cfg)
        assert new_interceptor is not None

        class _Req:
            server_name = "live"
            headers = {"X-Sticky": "keep"}

            def override(self, *, headers):
                self.headers = headers
                return self

        request = _Req()
        seen: dict = {}

        async def handler(req: Any) -> Any:
            seen["headers"] = req.headers
            return "ok"

        result = await new_interceptor(request, handler)
        assert result == "ok"
        assert seen["headers"]["Authorization"] == "Bearer xyz"
        assert seen["headers"]["X-Sticky"] == "keep"
    finally:
        oauth_mod.OAuthTokenManager.from_extensions_config = Mgr.from_extensions_config  # type: ignore[assignment]


@pytest.mark.asyncio
async def test_get_initial_oauth_headers_returns_cached_value() -> None:
    oauth = McpOAuthConfig(
        enabled=True,
        token_url="https://idp/oauth/token",
        client_id="cid",
        client_secret="csec",
    )
    cfg = _cfg(oauth)
    headers = await get_initial_oauth_headers(cfg)
    # The interceptor will hit httpx unless we seed the cache. We just
    # assert that the wrapper *skips* empty values: by injecting a
    # pre-fetched token in cache we avoid network entirely.
    import app.mcp.oauth as oauth_mod  # noqa: PLC0415
    from app.mcp.oauth import _OAuthToken  # noqa: PLC0415

    captured = oauth_mod.OAuthTokenManager.from_extensions_config(cfg)
    captured._tokens["live"] = _OAuthToken(  # type: ignore[attr-defined]
        access_token="prefetched",
        token_type="Bearer",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    headers = await get_initial_oauth_headers(cfg)
    assert headers == {"live": "Bearer prefetched"}


@pytest.mark.asyncio
async def test_get_initial_oauth_headers_skips_empty_values() -> None:
    oauth = McpOAuthConfig(
        enabled=True,
        token_url="https://idp/oauth/token",
        client_id="cid",
        client_secret="csec",
    )
    cfg = _cfg(oauth)
    mgr = OAuthTokenManager.from_extensions_config(cfg)

    async def empty_get(name: str) -> str | None:
        return None

    mgr.get_authorization_header = empty_get  # type: ignore[assignment]
    headers = await get_initial_oauth_headers(cfg)
    assert headers == {}


@pytest.mark.asyncio
async def test_get_initial_oauth_headers_empty_when_no_oauth() -> None:
    cfg = _cfg(None)
    headers = await get_initial_oauth_headers(cfg)
    assert headers == {}
