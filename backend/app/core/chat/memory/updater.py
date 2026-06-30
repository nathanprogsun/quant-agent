"""LLM-driven MemoryUpdater (P4.5).

Ports deer-flow's ``agents/memory/updater.py`` contract, adapted to write to
Postgres ``UserMemory`` / ``MemoryFact`` (D4). The updater is pure logic with
no DB import at construction time; persistence goes through ``apply`` which
receives a session factory from the MemoryUpdateQueue.

Contract: ``update_from_conversation(messages)`` returns a ``MemoryUpdateResult``
with the four canonical keys ``{user, history, newFacts, factsToRemove}``.
The LLM response is validated against a frozenset of required keys; facts below
``fact_confidence_threshold`` are dropped unless their category is in
``guaranteed_categories``.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID, uuid4

from langchain_core.messages import BaseMessage
from sqlalchemy import delete

from app.config.memory_config import MemoryConfig
from app.core.chat.memory.prompt import MEMORY_UPDATE_PROMPT
from app.db.dao.memory_repository import MemoryRepository
from app.db.models.memory import MemoryFact, UserMemory

logger = logging.getLogger(__name__)

REQUIRED_KEYS: frozenset[str] = frozenset({"user", "history", "newFacts", "factsToRemove"})

LLMClient = Callable[[str], Awaitable[str]]


class SessionFactoryProtocol(Protocol):
    """Minimal async session factory protocol."""

    def __call__(self) -> Any: ...


@dataclass(frozen=True)
class NewFact:
    """A fact proposed by the LLM."""

    content: str
    fact_type: str = "user"
    category: str = "general"
    confidence: float = 1.0


@dataclass(frozen=True)
class ExistingFact:
    """An already-stored fact (for pruning decisions)."""

    id: str
    content: str
    created_at: datetime
    category: str = "general"
    confidence: float = 1.0


@dataclass(frozen=True)
class MemoryUpdateResult:
    """Result of an LLM memory update pass."""

    user: str
    history: list[str] = field(default_factory=list)
    newFacts: list[NewFact] = field(default_factory=list)
    factsToRemove: list[str] = field(default_factory=list)


def _conversation_text(messages: list[BaseMessage]) -> str:
    lines: list[str] = []
    for msg in messages:
        role = getattr(msg, "type", "message")
        content = msg.content if isinstance(msg.content, str) else str(msg.content)
        lines.append(f"{role}: {content}")
    return "\n".join(lines)


def _strip_fence(raw: str) -> str:
    raw = raw.strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", raw, re.DOTALL)
    return fence.group(1) if fence else raw


def _parse_json(raw: str) -> dict[str, Any]:
    try:
        data = json.loads(_strip_fence(raw))
    except json.JSONDecodeError as e:
        raise ValueError(f"Memory LLM returned invalid JSON: {e}") from e
    if not isinstance(data, dict):
        raise ValueError("Memory LLM JSON must be a mapping")
    return data


def _validate_required(data: dict[str, Any]) -> None:
    missing = REQUIRED_KEYS - data.keys()
    if missing:
        raise ValueError(f"Memory LLM response missing keys: {sorted(missing)}")


def _coerce_new_facts(raw: Any) -> list[NewFact]:
    if not isinstance(raw, list):
        return []
    facts: list[NewFact] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        content = str(item.get("content", "")).strip()
        if not content:
            continue
        facts.append(
            NewFact(
                content=content,
                fact_type=str(item.get("fact_type", "user")),
                category=str(item.get("category", "general")),
                confidence=float(item.get("confidence", 1.0)),
            )
        )
    return facts


def _confidence_gated(facts: list[NewFact], config: MemoryConfig) -> list[NewFact]:
    guaranteed = set(config.guaranteed_categories)
    threshold = config.fact_confidence_threshold
    return [f for f in facts if f.confidence >= threshold or f.category in guaranteed]


def prune_facts(
    existing: list[ExistingFact], new_facts: list[NewFact], *, max_facts: int
) -> list[str]:
    """Return ids of existing facts to remove so total <= max_facts.

    Oldest existing facts (by ``created_at``) are pruned first. New facts are
    kept (they were just extracted as relevant). Returns [] when under limit.
    """
    total = len(existing) + len(new_facts)
    if total <= max_facts:
        return []
    to_remove = total - max_facts
    oldest = sorted(existing, key=lambda f: f.created_at)
    return [f.id for f in oldest[:to_remove]]


class MemoryUpdater:
    """LLM-driven memory evolution.

    Args:
        llm: Async callable that takes a prompt string and returns the LLM's
            raw text response.
        config: MemoryConfig (thresholds, categories, max_facts).
    """

    def __init__(self, *, llm: LLMClient, config: MemoryConfig) -> None:
        self._llm = llm
        self._config = config

    async def update_from_conversation(
        self,
        messages: list[BaseMessage],
        *,
        existing_facts: list[ExistingFact] | None = None,
    ) -> MemoryUpdateResult:
        """Run the LLM memory pass and return a validated, gated result."""
        prompt = MEMORY_UPDATE_PROMPT.replace("{conversation}", _conversation_text(messages))
        raw = await self._llm(prompt)
        data = _parse_json(raw)
        _validate_required(data)

        new_facts = _confidence_gated(_coerce_new_facts(data.get("newFacts")), self._config)
        facts_to_remove: list[str] = [str(x) for x in (data.get("factsToRemove") or []) if x]

        existing = existing_facts or []
        pruned = prune_facts(existing, new_facts, max_facts=self._config.max_facts)
        facts_to_remove.extend(pruned)

        return MemoryUpdateResult(
            user=str(data.get("user", "")),
            history=[str(h) for h in (data.get("history") or [])],
            newFacts=new_facts,
            factsToRemove=facts_to_remove,
        )

    async def apply(
        self,
        user_id: UUID,
        result: MemoryUpdateResult,
        session_factory: SessionFactoryProtocol,
    ) -> None:
        """Persist a result to Postgres via MemoryRepository."""
        async with session_factory() as session:
            repo = MemoryRepository(session=session)
            for fact in result.newFacts:
                repo.session.add(
                    MemoryFact(
                        id=uuid4(),
                        user_id=user_id,
                        fact_type=fact.fact_type,
                        content=fact.content,
                        created_at=datetime.utcnow(),
                    )
                )
            await repo.session.flush()
            for content in result.factsToRemove:
                await repo.session.execute(
                    delete(MemoryFact).where(
                        MemoryFact.user_id == user_id,
                        MemoryFact.content == content,
                    )
                )
            await repo.session.flush()
            if result.user:
                repo.session.add(
                    UserMemory(
                        id=uuid4(),
                        user_id=user_id,
                        memory_type="profile",
                        content=result.user,
                        confidence=1.0,
                        source="memory_updater",
                        created_at=datetime.utcnow(),
                    )
                )
                await repo.session.flush()
            await session.commit()


__all__ = [
    "REQUIRED_KEYS",
    "ExistingFact",
    "LLMClient",
    "MemoryUpdateResult",
    "MemoryUpdater",
    "NewFact",
    "prune_facts",
]
