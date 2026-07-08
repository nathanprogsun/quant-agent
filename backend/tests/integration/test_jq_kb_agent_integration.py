"""Lead agent integration — jq_kb wiring."""

from __future__ import annotations

from unittest.mock import patch

from app.core.chat.agent.lead_agent import make_lead_agent
from app.core.jq_kb.tools import get_tools


def test_lead_agent_pr3_tool_whitelist() -> None:
    tools = get_tools(pr_phase=3)
    names = {t.name for t in tools}
    assert names == {"search_jq_api", "search_jq_dict", "search_jq_strategy"}


def test_make_lead_agent_builds_middlewares() -> None:
    with (
        patch("app.core.chat.agent.lead_agent.PatchedChat"),
        patch("app.core.chat.agent.lead_agent.create_agent") as ca,
        patch("app.core.chat.agent.lead_agent.build_middlewares") as build_middlewares,
    ):
        ca.return_value = object()
        build_middlewares.return_value = []
        make_lead_agent({"configurable": {}})

    build_middlewares.assert_called_once()
