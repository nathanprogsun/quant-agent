"""MemoryRepository ORM tests."""
from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest

from app.db.dao.memory_repository import MemoryRepository
from app.db.models import MemoryFact, UserMemory

pytestmark = pytest.mark.asyncio


async def test_create_and_list_memory(session: Any) -> None:
    repo = MemoryRepository(session)
    user = uuid4()
    m = UserMemory(id=uuid4(), user_id=user, memory_type="preference", content="likes X")
    await repo.create_memory(m)

    items = await repo.find_memories_by_user(user)
    assert len(items) == 1
    assert items[0].content == "likes X"


async def test_filter_memory_by_type(session: Any) -> None:
    repo = MemoryRepository(session)
    user = uuid4()
    await repo.create_memory(
        UserMemory(id=uuid4(), user_id=user, memory_type="preference", content="p")
    )
    await repo.create_memory(
        UserMemory(id=uuid4(), user_id=user, memory_type="fact", content="f")
    )
    prefs = await repo.find_memories_by_user(user, memory_type="preference")
    assert len(prefs) == 1
    assert prefs[0].memory_type == "preference"


async def test_create_fact_with_embedding(session: Any) -> None:
    repo = MemoryRepository(session)
    user = uuid4()
    f = MemoryFact(
        id=uuid4(), user_id=user, fact_type="knowledge", content="c", embedding=[0.1, 0.2, 0.3]
    )
    await repo.create_fact(f)

    found = await repo.find_fact_by_id(f.id, user)
    assert found is not None
    assert found.embedding == [0.1, 0.2, 0.3]


async def test_delete_fact_only_owner(session: Any) -> None:
    repo = MemoryRepository(session)
    user = uuid4()
    other = uuid4()
    f = MemoryFact(id=uuid4(), user_id=user, fact_type="x", content="x")
    await repo.create_fact(f)

    assert (await repo.delete_fact(f.id, other)) is False
    assert (await repo.delete_fact(f.id, user)) is True
