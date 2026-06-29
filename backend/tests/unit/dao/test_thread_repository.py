"""ThreadRepository ORM tests (soft-delete semantics)."""
from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest

from app.common.exception.exception import ResourceNotFoundError
from app.db.dao.thread_repository import ThreadRepository
from app.db.models import Thread

pytestmark = pytest.mark.asyncio


def _thread(user_id: UUID | None = None) -> Thread:
    return Thread(
        id=uuid4(),
        user_id=user_id or uuid4(),
        title="t",
        model_name=None,
    )


async def test_create_and_find_by_id(session: Any) -> None:
    repo = ThreadRepository(session)
    t = await repo.create(_thread())
    found = await repo.find_by_id(t.id)
    assert found is not None
    assert found.title == "t"


async def test_soft_delete_hides_from_find(session: Any) -> None:
    repo = ThreadRepository(session)
    t = await repo.create(_thread())
    assert await repo.soft_delete(t.id, t.user_id) is True
    assert await repo.find_by_id(t.id) is None


async def test_list_by_user_id_orders_by_recent(session: Any) -> None:
    repo = ThreadRepository(session)
    user = uuid4()
    a = await repo.create(_thread(user_id=user))
    # Create b and immediately update it to ensure b.updated_at > a.created_at
    b = await repo.create(_thread(user_id=user))
    await repo.update_title(b.id, user, "b")
    # Update a to have updated_at older than b's updated_at
    await repo.update_title(a.id, user, "a")
    items = await repo.list_by_user_id(user)
    # b has newer updated_at, so b comes first despite being created earlier
    assert [t.id for t in items] == [b.id, a.id]


async def test_update_title_returns_updated_thread(session: Any) -> None:
    repo = ThreadRepository(session)
    t = await repo.create(_thread())
    updated = await repo.update_title(t.id, t.user_id, "new")
    assert updated is not None
    assert updated.title == "new"


async def test_find_by_id_and_user_or_fail_raises(session: Any) -> None:
    repo = ThreadRepository(session)
    with pytest.raises(ResourceNotFoundError):
        await repo.find_by_id_and_user_or_fail(uuid4(), uuid4())
