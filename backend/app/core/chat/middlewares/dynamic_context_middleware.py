"""Dynamic context injection middleware — frozen-snapshot ID-swap.

Ports deer-flow's dynamic_context_middleware.py:125-307 frozen-snapshot
pattern, ADAPTED to quant-agent's before_model hook (quant-agent uses a
manual StateGraph agent_node, not langchain create_agent, so deer-flow's
before_agent maps to before_model here).

First turn
----------
Finds the first user HumanMessage and replaces it IN-PLACE (same id) with
a SystemMessage <system-reminder> carrying the current date. The original
user text is re-emitted as HumanMessage(id="{stable_id}__user"). The
injected block is then FROZEN — its content never changes again, so the
prefix cache hits on every subsequent turn.

Midnight crossing
-----------------
If the current date differs from the last injected date, a lightweight
date-update SystemMessage is spliced in before the current (last)
HumanMessage (also via id-swap) and persisted. Subsequent turns on the
new day see the corrected date and skip re-injection.

Date granularity is DAY (%Y-%m-%d, %A), never second. Framework-owned
data (date) uses SystemMessage; memory (P4.4) will use HumanMessage with
id="{stable_id}__memory" (OWASP LLM01 role separation).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from app.core.chat.middlewares.base import AgentMiddleware

_REMINDER_KWARG = "dynamic_context_reminder"
_REMINDER_DATE_KEY = "reminder_date"


def _current_date() -> str:
    """Current date at day granularity. Monkeypatched in tests."""
    return datetime.now().strftime("%Y-%m-%d, %A")


def _date_reminder(date_str: str) -> str:
    return "\n".join(
        ("<system-reminder>", f"<current_date>{date_str}</current_date>", "</system-reminder>")
    )


def _is_reminder(msg: object) -> bool:
    return isinstance(msg, (HumanMessage, SystemMessage)) and bool(
        msg.additional_kwargs.get(_REMINDER_KWARG)
    )


def _last_injected_date(messages: list[BaseMessage]) -> str | None:
    """Most recently injected date, read from additional_kwargs (not content)."""
    for m in reversed(messages):
        if not _is_reminder(m):
            continue
        d = m.additional_kwargs.get(_REMINDER_DATE_KEY)
        if isinstance(d, str) and d:
            return d
    return None


def _is_user_injection_target(msg: object) -> bool:
    if not isinstance(msg, HumanMessage):
        return False
    if _is_reminder(msg):
        return False
    # Prevent recursive ID-swap on already-rewritten __user messages
    # (would cause id__user__user... suffix growth and ghost re-execution).
    return not (msg.id and str(msg.id).endswith("__user"))


def _make_reminder_and_user(
    original: HumanMessage, reminder_content: str, *, reminder_date: str
) -> list[BaseMessage]:
    """ID-swap triple: SystemMessage takes the original id; user text -> {id}__user."""
    stable_id = original.id or str(uuid.uuid4())
    return [
        SystemMessage(
            content=reminder_content,
            id=stable_id,
            additional_kwargs={
                _REMINDER_KWARG: True,
                _REMINDER_DATE_KEY: reminder_date,
                "hide_from_ui": True,
            },
        ),
        HumanMessage(
            content=original.content,
            id=f"{stable_id}__user",
            name=original.name,
            additional_kwargs=original.additional_kwargs,
        ),
    ]


class DynamicContextMiddleware(AgentMiddleware):
    """Frozen-snapshot date injection via ID-swap (deer-flow port)."""

    async def before_model(
        self, state: dict[str, Any], config: dict[str, Any]
    ) -> dict[str, Any] | None:
        messages = list(state.get("messages", []))
        if not messages:
            return None

        current_date = _current_date()
        last_date = _last_injected_date(messages)

        if last_date is None:
            # First turn: inject full reminder at the first user HumanMessage
            first_idx = next(
                (i for i, m in enumerate(messages) if _is_user_injection_target(m)), None
            )
            if first_idx is None:
                return None
            triple = _make_reminder_and_user(
                messages[first_idx],
                _date_reminder(current_date),
                reminder_date=current_date,
            )
            new_messages = messages[:first_idx] + triple + messages[first_idx + 1 :]
            return {"messages": new_messages}

        if last_date == current_date:
            # Same day: frozen — nothing to do
            return None

        # Midnight crossed: inject date-update at the last user HumanMessage
        last_idx = next(
            (i for i in reversed(range(len(messages))) if _is_user_injection_target(messages[i])),
            None,
        )
        if last_idx is None:
            return None
        triple = _make_reminder_and_user(
            messages[last_idx],
            _date_reminder(current_date),
            reminder_date=current_date,
        )
        new_messages = messages[:last_idx] + triple + messages[last_idx + 1 :]
        return {"messages": new_messages}
