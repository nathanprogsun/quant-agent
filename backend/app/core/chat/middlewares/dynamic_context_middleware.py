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

from langchain.agents.middleware import AgentMiddleware
from langgraph.runtime import Runtime
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from app.config.memory_config import MemoryConfig
from app.core.chat.memory.provider import MemoryProvider, get_memory_provider
from app.settings import get_settings

_REMINDER_KWARG = "dynamic_context_reminder"
_REMINDER_DATE_KEY = "reminder_date"

# Suffixes that mark a HumanMessage as already-id-swapped; the middleware must
# not treat these as fresh injection targets (would cause suffix growth / ghosts).
_USER_SUFFIX = "__user"
_MEMORY_SUFFIX = "__memory"


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
    # Prevent recursive ID-swap on already-rewritten messages (would cause
    # id__user__user... suffix growth and ghost re-execution).
    if msg.id:
        mid = str(msg.id)
        if mid.endswith((_USER_SUFFIX, _MEMORY_SUFFIX)):
            return False
    return True


def _make_reminder_and_user(
    original: HumanMessage,
    reminder_content: str,
    *,
    reminder_date: str,
    memory_block: str | None = None,
) -> list[BaseMessage]:
    """ID-swap block: SystemMessage takes the original id; user text -> {id}__user.

    When ``memory_block`` is provided, an extra ``HumanMessage(id='{id}__memory')``
    is emitted between the SystemMessage reminder and the ``{id}__user`` message.
    The memory HumanMessage deliberately carries NO ``reminder_date`` (OWASP LLM01:
    framework-owned date stays in SystemMessage; user-owned memory stays HumanMessage).
    """
    stable_id = original.id or str(uuid.uuid4())
    messages: list[BaseMessage] = [
        SystemMessage(
            content=reminder_content,
            id=stable_id,
            additional_kwargs={
                _REMINDER_KWARG: True,
                _REMINDER_DATE_KEY: reminder_date,
                "hide_from_ui": True,
            },
        ),
    ]
    if memory_block:
        messages.append(
            HumanMessage(
                content=memory_block,
                id=f"{stable_id}{_MEMORY_SUFFIX}",
                additional_kwargs={"hide_from_ui": True},
            )
        )
    messages.append(
        HumanMessage(
            content=original.content,
            id=f"{stable_id}{_USER_SUFFIX}",
            name=original.name,
            additional_kwargs=original.additional_kwargs,
        )
    )
    return messages


class DynamicContextMiddleware(AgentMiddleware):
    """Frozen-snapshot date + memory injection via ID-swap (deer-flow port).

    Args:
        memory_config: MemoryConfig override (default: settings.memory). Used to
            gate memory injection via ``injection_enabled``.
        memory_provider: MemoryProvider override (default: global provider set
            by lifespan). Returns the ``<memory>`` block for a user.
    """

    def __init__(
        self,
        *,
        memory_config: MemoryConfig | None = None,
        memory_provider: MemoryProvider | None = None,
    ) -> None:
        self._memory_config = memory_config
        self._memory_provider = memory_provider

    def _resolve_config(self) -> MemoryConfig:
        return self._memory_config or get_settings().memory

    def _resolve_provider(self) -> MemoryProvider | None:
        if self._memory_provider is not None:
            return self._memory_provider
        return get_memory_provider()

    async def _resolve_memory_block(self) -> str | None:
        """Fetch the memory block iff injection is enabled and a provider exists."""
        cfg = self._resolve_config()
        if not cfg.injection_enabled:
            return None
        provider = self._resolve_provider()
        if provider is None:
            return None
        # user_id is not available from Runtime (agent_node passes Runtime()).
        # The provider is responsible for user resolution.
        return await provider.get_block(None)

    async def abefore_model(self, state: dict[str, Any], runtime: Runtime) -> dict[str, Any] | None:
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
            memory_block = await self._resolve_memory_block()
            triple = _make_reminder_and_user(
                messages[first_idx],
                _date_reminder(current_date),
                reminder_date=current_date,
                memory_block=memory_block,
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
        memory_block = await self._resolve_memory_block()
        triple = _make_reminder_and_user(
            messages[last_idx],
            _date_reminder(current_date),
            reminder_date=current_date,
            memory_block=memory_block,
        )
        new_messages = messages[:last_idx] + triple + messages[last_idx + 1 :]
        return {"messages": new_messages}
