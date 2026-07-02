"""DynamicContextMiddleware memory injection extension (P4.2).

Extends the P0.2 frozen-snapshot ID-swap: when ``memory.injection_enabled`` is
True and a memory block is available, the middleware emits
``HumanMessage(id='{stable_id}__memory')`` between the SystemMessage reminder
and ``{stable_id}__user``. The memory HumanMessage never carries
``reminder_date`` (OWASP LLM01 — framework date in SystemMessage, user memory
in HumanMessage).
"""

from __future__ import annotations

from typing import Any

import pytest
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.runtime import Runtime

from app.config.memory_config import MemoryConfig
from app.core.chat.middlewares.dynamic_context_middleware import (
    _REMINDER_DATE_KEY,
    _REMINDER_KWARG,
    DynamicContextMiddleware,
)


class _FakeProvider:
    def __init__(self, block: str | None = "<memory>用户偏好低波动</memory>") -> None:
        self._block = block
        self.calls: list[Any] = []

    async def get_block(self, user_id: Any) -> str | None:
        self.calls.append(user_id)
        return self._block


def _state_with_first_user() -> dict[str, Any]:
    return {"messages": [SystemMessage(content="sys"), HumanMessage(content="hello", id="u1")]}


@pytest.mark.asyncio
async def test_memory_human_message_emitted_when_injection_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.core.chat.middlewares.dynamic_context_middleware._current_date",
        lambda: "2026-06-30, Monday",
    )
    provider = _FakeProvider()
    mw = DynamicContextMiddleware(
        memory_config=MemoryConfig(injection_enabled=True),
        memory_provider=provider,
    )
    out = await mw.abefore_model(_state_with_first_user(), Runtime())
    assert out is not None
    msgs = out["messages"]

    memory_msgs = [m for m in msgs if isinstance(m, HumanMessage) and m.id == "u1__memory"]
    assert len(memory_msgs) == 1
    assert memory_msgs[0].content == "<memory>用户偏好低波动</memory>"
    # OWASP LLM01: memory HumanMessage never carries reminder_date or reminder kwarg.
    assert _REMINDER_DATE_KEY not in memory_msgs[0].additional_kwargs
    assert not memory_msgs[0].additional_kwargs.get(_REMINDER_KWARG)


@pytest.mark.asyncio
async def test_no_memory_human_message_when_injection_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.core.chat.middlewares.dynamic_context_middleware._current_date",
        lambda: "2026-06-30, Monday",
    )
    provider = _FakeProvider()
    mw = DynamicContextMiddleware(
        memory_config=MemoryConfig(injection_enabled=False),
        memory_provider=provider,
    )
    out = await mw.abefore_model(_state_with_first_user(), Runtime())
    assert out is not None
    msgs = out["messages"]
    assert not any(isinstance(m, HumanMessage) and m.id == "u1__memory" for m in msgs)
    # Provider must not be consulted when injection is disabled.
    assert provider.calls == []


@pytest.mark.asyncio
async def test_memory_message_absent_when_provider_returns_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.core.chat.middlewares.dynamic_context_middleware._current_date",
        lambda: "2026-06-30, Monday",
    )
    mw = DynamicContextMiddleware(
        memory_config=MemoryConfig(injection_enabled=True),
        memory_provider=_FakeProvider(block=None),
    )
    out = await mw.abefore_model(_state_with_first_user(), Runtime())
    msgs = out["messages"]
    assert not any(isinstance(m, HumanMessage) and m.id == "u1__memory" for m in msgs)
    # Date reminder + __user still present.
    assert any(isinstance(m, SystemMessage) and m.id == "u1" for m in msgs)
    assert any(isinstance(m, HumanMessage) and m.id == "u1__user" for m in msgs)


@pytest.mark.asyncio
async def test_memory_message_ordering_between_reminder_and_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.core.chat.middlewares.dynamic_context_middleware._current_date",
        lambda: "2026-06-30, Monday",
    )
    mw = DynamicContextMiddleware(
        memory_config=MemoryConfig(injection_enabled=True),
        memory_provider=_FakeProvider(),
    )
    out = await mw.abefore_model(_state_with_first_user(), Runtime())
    msgs = out["messages"]
    ids = [m.id for m in msgs]
    # Reminder (u1) -> memory (u1__memory) -> user (u1__user), in that order.
    assert ids.index("u1") < ids.index("u1__memory") < ids.index("u1__user")
