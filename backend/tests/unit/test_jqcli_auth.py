"""Tests for jqcli credential resolution."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.core.backtest.jqcli_auth import (
    clear_jqcli_credentials_cache,
    has_jqcli_configuration,
    resolve_jqcli_credentials,
)
from app.settings import get_settings, reload_settings


@pytest.fixture(autouse=True)
def _isolate_jqcli_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prevent backend/.env jqcli credentials from affecting unit tests."""
    monkeypatch.setenv("JQCLI_USERNAME", "")
    monkeypatch.setenv("JQCLI_PASSWORD", "")
    reload_settings()
    clear_jqcli_credentials_cache()
    yield
    clear_jqcli_credentials_cache()
    reload_settings()


def test_has_configuration_with_username_password(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JQCLI_USERNAME", "user")
    monkeypatch.setenv("JQCLI_PASSWORD", "pass")
    reload_settings()
    assert has_jqcli_configuration(get_settings()) is True


def test_has_configuration_false_when_empty() -> None:
    assert has_jqcli_configuration(get_settings()) is False


def test_has_configuration_false_when_password_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JQCLI_USERNAME", "user")
    reload_settings()
    assert has_jqcli_configuration(get_settings()) is False


@patch("app.core.backtest.jqcli_auth.login_with_password")
def test_resolve_logs_in_with_username_password(
    mock_login,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock_login.return_value = {"cookie": "session=logged-in"}
    monkeypatch.setenv("JQCLI_USERNAME", "176000")
    monkeypatch.setenv("JQCLI_PASSWORD", "secret")
    reload_settings()

    creds = resolve_jqcli_credentials(get_settings())

    assert creds is not None
    assert creds.cookie == "session=logged-in"
    assert creds.username == "176000"
    mock_login.assert_called_once()


@patch("app.core.backtest.jqcli_auth.login_with_password")
def test_resolve_uses_cache_within_ttl(mock_login, monkeypatch: pytest.MonkeyPatch) -> None:
    mock_login.return_value = {"cookie": "session=logged-in"}
    monkeypatch.setenv("JQCLI_USERNAME", "176000")
    monkeypatch.setenv("JQCLI_PASSWORD", "secret")
    monkeypatch.setenv("JQCLI_AUTH_CACHE_TTL_SECONDS", "3600")
    reload_settings()
    settings = get_settings()

    first = resolve_jqcli_credentials(settings)
    second = resolve_jqcli_credentials(settings)

    assert first == second
    mock_login.assert_called_once()


@patch("app.core.backtest.jqcli_auth.login_with_password")
def test_resolve_raises_when_login_returns_empty_cookie(
    mock_login,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock_login.return_value = {"cookie": ""}
    monkeypatch.setenv("JQCLI_USERNAME", "176000")
    monkeypatch.setenv("JQCLI_PASSWORD", "secret")
    reload_settings()

    with pytest.raises(RuntimeError, match="cookie"):
        resolve_jqcli_credentials(get_settings())
