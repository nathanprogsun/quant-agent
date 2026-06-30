"""Tests for SubagentsAppConfig — subagent settings layered resolution.

Ports deer-flow's config/subagents_config.py:71-143 (Pydantic model). Each
test asserts a specific property of the layering/limits resolver surface.
"""

from __future__ import annotations

from app.config.subagents_config import (
    CustomSubagentConfig,
    SubagentOverrideConfig,
    SubagentsAppConfig,
)


def test_default_timeout_seconds_is_1800() -> None:
    cfg = SubagentsAppConfig()
    assert cfg.timeout_seconds == 1800


def test_default_max_turns_is_none() -> None:
    cfg = SubagentsAppConfig()
    assert cfg.max_turns is None


def test_get_timeout_for_uses_global_by_default() -> None:
    cfg = SubagentsAppConfig(timeout_seconds=1234)
    assert cfg.get_timeout_for("any-agent") == 1234


def test_get_timeout_for_layered_override() -> None:
    cfg = SubagentsAppConfig(
        timeout_seconds=1800,
        agents={"general-purpose": SubagentOverrideConfig(timeout_seconds=600)},
    )
    assert cfg.get_timeout_for("general-purpose") == 600
    assert cfg.get_timeout_for("other-agent") == 1800


def test_get_model_for_returns_override_only() -> None:
    cfg = SubagentsAppConfig(
        agents={"foo": SubagentOverrideConfig(model="gpt-4o")},
    )
    assert cfg.get_model_for("foo") == "gpt-4o"
    assert cfg.get_model_for("bar") is None


def test_get_max_turns_layered() -> None:
    cfg = SubagentsAppConfig(
        max_turns=10,
        agents={"foo": SubagentOverrideConfig(max_turns=99)},
    )
    assert cfg.get_max_turns_for("foo", builtin_default=50) == 99
    assert cfg.get_max_turns_for("bar", builtin_default=50) == 10


def test_custom_agent_full_schema() -> None:
    """Custom agents carry description, system_prompt, tools, disallowed, etc."""
    cfg = SubagentsAppConfig(
        custom_agents={
            "research": CustomSubagentConfig(
                description="Research tasks",
                system_prompt="You are a researcher.",
                tools=["web_search"],
                disallowed_tools=["task"],
                model="gpt-4o",
                max_turns=25,
                timeout_seconds=900,
            )
        }
    )
    c = cfg.custom_agents["research"]
    assert c.description == "Research tasks"
    assert c.system_prompt == "You are a researcher."
    assert c.tools == ["web_search"]
    assert c.disallowed_tools == ["task"]
    assert c.model == "gpt-4o"
    assert c.max_turns == 25
    assert c.timeout_seconds == 900


def test_get_skills_for_returns_override() -> None:
    cfg = SubagentsAppConfig(
        agents={"foo": SubagentOverrideConfig(skills=["a", "b"])},
    )
    assert cfg.get_skills_for("foo") == ["a", "b"]
    assert cfg.get_skills_for("other") is None
