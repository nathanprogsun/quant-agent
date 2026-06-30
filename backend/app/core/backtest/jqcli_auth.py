"""JoinQuant jqcli credential resolution via username/password login and caching."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass

from jqcli.api.auth import login_with_password

from app.settings import Settings, get_settings


class JqcliNotConfiguredError(Exception):
    """Raised when JQCLI_USERNAME/JQCLI_PASSWORD are not set in the environment."""


@dataclass(frozen=True)
class JqcliCredentials:
    """Resolved jqcli credentials for ApiClient."""

    token: str
    cookie: str
    api_base: str
    username: str | None = None


@dataclass
class _CredentialCache:
    credentials: JqcliCredentials
    expires_at: float


_cache: _CredentialCache | None = None
_cache_lock = threading.Lock()


def _secret_value(value: object | None) -> str:
    if value is None:
        return ""
    if hasattr(value, "get_secret_value"):
        return str(value.get_secret_value()).strip()
    return str(value).strip()


def clear_jqcli_credentials_cache() -> None:
    """Clear in-memory login cache (for tests)."""
    global _cache
    with _cache_lock:
        _cache = None


def _login_with_password(
    api_base: str,
    username: str,
    password: str,
) -> JqcliCredentials:
    result = login_with_password(api_base, username, password, timeout=30)
    cookie = str(result.get("cookie", "")).strip()
    if not cookie:
        raise RuntimeError("聚宽登录失败：未返回 cookie")
    return JqcliCredentials(
        token="",
        cookie=cookie,
        api_base=api_base,
        username=username,
    )


def _get_cached_or_login(
    *,
    api_base: str,
    username: str,
    password: str,
    cache_ttl_seconds: int,
) -> JqcliCredentials:
    global _cache
    now = time.monotonic()
    with _cache_lock:
        if _cache is not None and _cache.expires_at > now:
            return _cache.credentials

    credentials = _login_with_password(api_base, username, password)

    with _cache_lock:
        _cache = _CredentialCache(
            credentials=credentials,
            expires_at=now + cache_ttl_seconds,
        )
    return credentials


def has_jqcli_configuration(settings: Settings) -> bool:
    """Return True when JQCLI_USERNAME and JQCLI_PASSWORD are configured."""
    username = _secret_value(settings.jqcli_username)
    password = _secret_value(settings.jqcli_password)
    return bool(username and password)


def resolve_jqcli_credentials(settings: Settings | None = None) -> JqcliCredentials | None:
    """Resolve jqcli credentials by logging in with JQCLI_USERNAME/JQCLI_PASSWORD.

    Raises:
        JqcliNotConfiguredError: when username or password is not set.

    Returns:
        ``None`` when credentials are configured but login fails.
    """
    cfg = settings or get_settings()
    api_base = cfg.jqcli_api_base

    username = _secret_value(cfg.jqcli_username)
    password = _secret_value(cfg.jqcli_password)
    if not username or not password:
        raise JqcliNotConfiguredError(
            "JQCLI_USERNAME and JQCLI_PASSWORD are not configured",
        )

    return _get_cached_or_login(
        api_base=api_base,
        username=username,
        password=password,
        cache_ttl_seconds=cfg.jqcli_auth_cache_ttl_seconds,
    )


def resolve_jqcli_credentials_tuple(
    settings: Settings | None = None,
) -> tuple[str, str, str] | None:
    """Return (token, cookie, api_base) for BacktestService compatibility."""
    creds = resolve_jqcli_credentials(settings)
    if creds is None:
        return None
    return creds.token, creds.cookie, creds.api_base
