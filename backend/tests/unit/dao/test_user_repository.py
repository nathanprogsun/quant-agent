"""UserRepository ORM tests."""
from __future__ import annotations

from typing import Any

import pytest

from app.common.exception.exception import ConflictResourceError
from app.db.dao.user_repository import UserRepository
from app.db.models import User

pytestmark = pytest.mark.asyncio


def _new_user(**overrides: Any) -> User:
    base: dict[str, Any] = dict(
        email="alice@test.com",
        username="alice",
        full_name="Alice",
        hashed_password="x",
    )
    base.update(overrides)
    return User(**base)


async def test_create_and_find_by_email(session: Any) -> None:
    repo = UserRepository(session)
    user = await repo.create(_new_user())
    assert user.id is not None

    found = await repo.find_by_email("alice@test.com")
    assert found is not None
    assert found.id == user.id


async def test_create_duplicate_email_raises(session: Any) -> None:
    repo = UserRepository(session)
    await repo.create(_new_user())
    with pytest.raises(ConflictResourceError):
        await repo.create(_new_user(email="alice@test.com", username="alice2"))


async def test_count_active_filters_inactive(session: Any) -> None:
    repo = UserRepository(session)
    await repo.create(_new_user(email="a@x.com", username="a"))
    await repo.create(_new_user(email="b@x.com", username="b"))
    b_user = await repo.find_by_email("b@x.com")
    assert b_user is not None
    await repo.delete(b_user.id, soft=True)

    assert await repo.count_all() == 2
    assert await repo.count_active() == 1


async def test_bump_token_version_increments(session: Any) -> None:
    repo = UserRepository(session)
    user = await repo.create(_new_user())
    initial = user.token_version

    ok = await repo.bump_token_version(user.id)
    assert ok

    reloaded = await repo.find_by_id(user.id)
    assert reloaded is not None
    assert reloaded.token_version == initial + 1
