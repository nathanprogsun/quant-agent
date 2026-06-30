"""Tests for MemoryUpdater — LLM-driven memory evolution (P4.5)."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

import pytest

from app.config.memory_config import MemoryConfig
from app.core.chat.memory.updater import (
    ExistingFact,
    MemoryUpdater,
    MemoryUpdateResult,
    NewFact,
    prune_facts,
)


async def _fake_llm_returning(payload: str) -> Callable[[str], Awaitable[str]]:
    async def _llm(_prompt: str) -> str:
        return payload

    return _llm


def _fact_payload(
    *,
    user: str = "investor",
    history: list[str] | None = None,
    new_facts: list[dict] | None = None,
    remove: list[str] | None = None,
) -> str:
    return json.dumps(
        {
            "user": user,
            "history": history or [],
            "newFacts": new_facts or [],
            "factsToRemove": remove or [],
        }
    )


@pytest.mark.asyncio
async def test_update_returns_result_with_required_keys() -> None:
    llm = await _fake_llm_returning(
        _fact_payload(
            user="偏好ETF轮动",
            new_facts=[{"content": "偏好低波动", "confidence": 0.9}],
        )
    )
    updater = MemoryUpdater(llm=llm, config=MemoryConfig())
    result = await updater.update_from_conversation(messages=[])
    assert isinstance(result, MemoryUpdateResult)
    assert result.user == "偏好ETF轮动"
    assert result.newFacts == [NewFact(content="偏好低波动", confidence=0.9)]
    assert result.factsToRemove == []


@pytest.mark.asyncio
async def test_llm_response_validated_against_required_keys() -> None:
    llm = await _fake_llm_returning(
        '{"user": "x", "history": []}'
    )  # missing newFacts, factsToRemove
    updater = MemoryUpdater(llm=llm, config=MemoryConfig())
    with pytest.raises(ValueError):
        await updater.update_from_conversation(messages=[])


@pytest.mark.asyncio
async def test_confidence_threshold_gates_acceptance() -> None:
    llm = await _fake_llm_returning(
        _fact_payload(
            new_facts=[
                {"content": "high-conf", "confidence": 0.8},
                {"content": "low-conf", "confidence": 0.5},
                {"content": "correction", "confidence": 0.3, "category": "correction"},
            ]
        )
    )
    cfg = MemoryConfig(fact_confidence_threshold=0.7)
    updater = MemoryUpdater(llm=llm, config=cfg)
    result = await updater.update_from_conversation(messages=[])
    contents = {f.content for f in result.newFacts}
    assert contents == {"high-conf", "correction"}
    assert "low-conf" not in contents


def test_prune_facts_enforces_max_and_drops_oldest() -> None:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    existing = [
        ExistingFact(id=f"e{i}", content=f"old-{i}", created_at=base + timedelta(days=i))
        for i in range(95)
    ]
    new_facts = [NewFact(content=f"new-{i}", confidence=0.9) for i in range(10)]
    # 95 + 10 = 105 > max_facts=100 → 5 oldest existing must be pruned.
    to_remove = prune_facts(existing, new_facts, max_facts=100)
    assert len(to_remove) == 5
    assert to_remove == ["e0", "e1", "e2", "e3", "e4"]


def test_prune_facts_no_prune_under_limit() -> None:
    existing = [ExistingFact(id="e0", content="x", created_at=datetime.now(UTC))]
    new_facts = [NewFact(content="y", confidence=0.9)]
    assert prune_facts(existing, new_facts, max_facts=100) == []
