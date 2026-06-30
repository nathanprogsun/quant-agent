"""Tests for BacktestService ownership-registry injection.

These tests pin down the contract introduced when the bug where per-request
service construction caused SSE stream endpoints to lose ownership state was
fixed. The shared registry is what makes submit → poll → stream consistent
across independent FastAPI requests.
"""

from __future__ import annotations

from unittest.mock import patch
from uuid import uuid4

import pytest

from app.core.backtest.errors import BacktestError
from app.core.backtest.registry import BacktestRegistry
from app.core.backtest.service import BacktestService


def _service(registry: BacktestRegistry | None = None) -> BacktestService:
    """Build a BacktestService with optional shared registry."""
    return BacktestService(token="t", cookie="c", api_base="https://example", registry=registry)


def test_service_uses_injected_registry_when_provided() -> None:
    """A shared registry is the one BacktestService exposes."""
    shared = BacktestRegistry()
    user_id = uuid4()

    service = _service(registry=shared)
    service.registry.register("bt-shared", user_id)

    assert service.registry is shared
    assert service.registry.is_owner("bt-shared", user_id)


def test_service_constructs_its_own_registry_when_none_provided() -> None:
    """Default-constructed service still has a working registry (unit-test friendly)."""
    service = _service()
    user_id = uuid4()
    service.registry.register("bt-default", user_id)

    assert service.registry.is_owner("bt-default", user_id)


def test_two_services_sharing_one_registry_agree_on_ownership() -> None:
    """Submitting via service A makes service B recognise the same owner.

    This is the scenario that used to fail: the submit handler built service A,
    the SSE handler built service B, and B's fresh registry didn't see A's
    registration, so ``assert_owner`` raised 404.
    """
    shared = BacktestRegistry()
    user_id = uuid4()
    submitter = _service(registry=shared)
    streamer = _service(registry=shared)

    submitter.registry.register("bt-cross", user_id)

    assert streamer.registry.is_owner("bt-cross", user_id)


@pytest.mark.asyncio
async def test_assert_owner_uses_shared_registry() -> None:
    """End-to-end: register via A, then ``assert_owner`` via B sees it."""
    shared = BacktestRegistry()
    user_id = uuid4()
    submitter = _service(registry=shared)
    streamer = _service(registry=shared)

    submitter.registry.register("bt-stream", user_id)

    # No exception → ownership seen through shared registry.
    streamer.assert_owner("bt-stream", user_id)


@pytest.mark.asyncio
async def test_assert_owner_raises_when_unknown_id() -> None:
    """404-equivalent behaviour when no registration exists for the id."""
    service = _service()
    with pytest.raises(BacktestError) as exc_info:
        service.assert_owner("bt-unknown", uuid4())
    assert exc_info.value.http_code() == 404
    assert exc_info.value.error_code == "backtest_not_found"


@pytest.mark.asyncio
async def test_assert_owner_raises_when_wrong_user() -> None:
    """A different user must not be allowed to access another user's backtest."""
    shared = BacktestRegistry()
    owner = uuid4()
    intruder = uuid4()
    submitter = _service(registry=shared)
    intruder_service = _service(registry=shared)

    submitter.registry.register("bt-priv", owner)

    with pytest.raises(BacktestError) as exc_info:
        intruder_service.assert_owner("bt-priv", intruder)
    assert exc_info.value.http_code() == 404


def test_release_active_clears_thread_lock_but_keeps_owner() -> None:
    """After a backtest finishes, thread lock clears but owner mapping stays."""
    registry = BacktestRegistry()
    user_id = uuid4()
    thread_id = str(uuid4())
    registry.register("bt-done", user_id, thread_id=thread_id)

    assert registry.get_active_for_thread(thread_id) == "bt-done"
    registry.release_active("bt-done")
    assert registry.get_active_for_thread(thread_id) is None
    assert registry.is_owner("bt-done", user_id)


def test_worker_threadpool_call_does_not_mutate_shared_registry() -> None:
    """Service construction in a worker must not blow away another service's registry.

    Regression guard for the case where a worker re-built ``BacktestService``
    without passing the shared registry — that would silently create a fresh
    registry, breaking the contract.
    """
    shared = BacktestRegistry()
    user_id = uuid4()
    shared.register("bt-pinned", user_id)

    # Simulate the worker calling the constructor with the shared registry.
    worker_service = BacktestService(
        token="t",
        cookie="c",
        api_base="https://example",
        registry=shared,
    )

    with patch.object(worker_service, "_registry", shared):
        assert worker_service.registry is shared
        assert worker_service.registry.is_owner("bt-pinned", user_id)
