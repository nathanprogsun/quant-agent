"""DynamicContextMiddleware — frozen-snapshot ID-swap (deer-flow port).

First turn: the first user HumanMessage is replaced in-place (same id) by
a SystemMessage <system-reminder> carrying the current date; the original
user text is re-emitted as HumanMessage(id="{stable_id}__user"). The
injected block is FROZEN — content never changes on subsequent same-day
turns, so prefix cache hits every turn. Midnight crossing injects a
date-update reminder before the current (last) HumanMessage.
"""

from __future__ import annotations

from typing import Any

import pytest
from langchain_core.messages import HumanMessage, SystemMessage

from app.core.chat.middlewares.dynamic_context_middleware import (
    _REMINDER_DATE_KEY,
    _REMINDER_KWARG,
    DynamicContextMiddleware,
)


def _reminder(content: str, msg_id: str, date: str) -> SystemMessage:
    return SystemMessage(
        content=content,
        id=msg_id,
        additional_kwargs={
            _REMINDER_KWARG: True,
            _REMINDER_DATE_KEY: date,
            "hide_from_ui": True,
        },
    )


@pytest.mark.asyncio
async def test_first_turn_swaps_first_human_message_into_system_reminder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.core.chat.middlewares.dynamic_context_middleware._current_date",
        lambda: "2026-06-30, Monday",
    )
    mw = DynamicContextMiddleware()
    state: dict[str, Any] = {
        "messages": [SystemMessage(content="sys"), HumanMessage(content="hello", id="u1")]
    }
    out = await mw.before_model(state, {})
    assert out is not None
    msgs = out["messages"]
    # Original HumanMessage id="u1" is replaced by a SystemMessage reminder with the SAME id
    reminder = [m for m in msgs if isinstance(m, SystemMessage) and m.id == "u1"]
    assert len(reminder) == 1, (
        f"expected one reminder SystemMessage id=u1, got ids={[m.id for m in msgs]}"
    )
    assert "<current_date>2026-06-30, Monday</current_date>" in reminder[0].content
    # Original user text preserved as HumanMessage(id="u1__user")
    user_msg = [m for m in msgs if isinstance(m, HumanMessage) and m.id == "u1__user"]
    assert len(user_msg) == 1 and user_msg[0].content == "hello"
    # No leftover HumanMessage with the original id (it was swapped away)
    assert not any(isinstance(m, HumanMessage) and m.id == "u1" for m in msgs)


@pytest.mark.asyncio
async def test_same_day_subsequent_turn_is_frozen(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.core.chat.middlewares.dynamic_context_middleware._current_date",
        lambda: "2026-06-30, Monday",
    )
    mw = DynamicContextMiddleware()
    # State AFTER first turn (persisted): reminder + __user already present, plus a 2nd user msg
    state: dict[str, Any] = {
        "messages": [
            SystemMessage(content="sys"),
            _reminder(
                "<system-reminder>\n<current_date>2026-06-30, Monday</current_date>\n</system-reminder>",
                "u1",
                "2026-06-30, Monday",
            ),
            HumanMessage(content="hello", id="u1__user"),
            HumanMessage(content="second question", id="u2"),
        ]
    }
    out = await mw.before_model(state, {})
    # Frozen: same day → no patch
    assert out is None, "same-day subsequent turn must be frozen (no patch)"


@pytest.mark.asyncio
async def test_does_not_mutate_static_system_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.core.chat.middlewares.dynamic_context_middleware._current_date",
        lambda: "2026-06-30, Monday",
    )
    mw = DynamicContextMiddleware()
    sys_content = "static system prompt"
    state: dict[str, Any] = {
        "messages": [SystemMessage(content=sys_content), HumanMessage(content="hi", id="u1")]
    }
    out = await mw.before_model(state, {})
    msgs = out["messages"]
    # messages[0] static SystemMessage.content MUST be unchanged
    assert isinstance(msgs[0], SystemMessage)
    assert msgs[0].content == sys_content


@pytest.mark.asyncio
async def test_midnight_crossing_injects_date_update_at_last_human(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Persisted first-turn reminder is from yesterday; today is the next day
    monkeypatch.setattr(
        "app.core.chat.middlewares.dynamic_context_middleware._current_date",
        lambda: "2026-07-01, Tuesday",
    )
    mw = DynamicContextMiddleware()
    state: dict[str, Any] = {
        "messages": [
            SystemMessage(content="sys"),
            _reminder(
                "<system-reminder>\n<current_date>2026-06-30, Monday</current_date>\n</system-reminder>",
                "u1",
                "2026-06-30, Monday",
            ),
            HumanMessage(content="hello", id="u1__user"),
            HumanMessage(content="good morning", id="u2"),
        ]
    }
    out = await mw.before_model(state, {})
    assert out is not None
    msgs = out["messages"]
    # A NEW date-update SystemMessage reminder is injected with reminder_date=today
    updates = [
        m
        for m in msgs
        if isinstance(m, SystemMessage)
        and m.additional_kwargs.get(_REMINDER_DATE_KEY) == "2026-07-01, Tuesday"
    ]
    assert len(updates) == 1, f"expected one date-update reminder, got ids={[m.id for m in msgs]}"
    # It reuses the last HumanMessage id (u2) via id-swap
    assert updates[0].id == "u2"
    # Original last user text preserved as u2__user
    assert any(
        isinstance(m, HumanMessage) and m.id == "u2__user" and m.content == "good morning"
        for m in msgs
    )
