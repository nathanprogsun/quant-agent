"""Unit tests for agent layer — ThreadState, lead-agent assembly."""

from __future__ import annotations

from unittest.mock import patch

from langchain_core.messages import HumanMessage

from app.core.chat.agent.lead_agent import make_lead_agent
from app.core.chat.agent.thread_state import ThreadState

# ── ThreadState ──────────────────────────────────────────────


def test_thread_state_accepts_messages() -> None:
    """ThreadState accepts messages field with LangChain types."""
    state: ThreadState = {
        "messages": [HumanMessage(content="hello")],
    }
    assert len(state["messages"]) == 1
    assert state["messages"][0].content == "hello"


def test_thread_state_all_fields_optional() -> None:
    """ThreadState with total=False — empty dict is valid."""
    state: ThreadState = {}
    assert state.get("messages") is None
    assert state.get("title") is None
    assert state.get("code") is None


# ── make_lead_agent assembly ─────────────────────────────────


def test_make_lead_agent_requests_reasoning_split() -> None:
    """Lead agent model should split reasoning from answer at the provider.

    The model is constructed via ``PatchedChat`` (a ChatOpenAI subclass that
    surfaces reasoning deltas — see ADR-0001 / app/core/chat/llm/). The
    ``reasoning_split`` flag is forwarded via ``extra_body`` unchanged.
    """
    with (
        patch("app.core.chat.agent.lead_agent.PatchedChat") as patched_chat,
        patch("app.core.chat.agent.lead_agent.create_agent") as ca,
    ):
        ca.return_value = object()
        make_lead_agent({"configurable": {}})

    patched_chat.assert_called_once()
    assert patched_chat.call_args.kwargs["extra_body"] == {"reasoning_split": True}
