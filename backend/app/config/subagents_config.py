"""Subagent configuration (P3.5).

Boot-time configuration for the multi-subagent subsystem, ported from
deer-flow's ``config/subagents_config.py:71-143``.

Layering rule: ``agents.<name>`` (per-agent override) wins over the global
top-level field (``timeout_seconds``, ``max_turns``, ``model``, ``skills``).
``custom_agents`` declares user-defined subagent types with their own
``tools``, ``system_prompt``, and limits — used by the registry when an
LLM dispatches ``task(subagent_type=...)``.

Channel-level ``subagent_enabled`` (P3.5) lives on ``Settings`` directly
(``app/settings.py``) because it gates tool exposure per request, not per
agent. See ``ChannelConfig`` adapters elsewhere for the gating convention.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class SubagentOverrideConfig(BaseModel):
    """Per-agent configuration overrides layered atop the global defaults."""

    timeout_seconds: int | None = Field(
        default=None,
        ge=1,
        description="Timeout in seconds for this subagent (None = use global default)",
    )
    max_turns: int | None = Field(
        default=None,
        ge=1,
        description="Maximum turns for this subagent (None = use global or builtin default)",
    )
    model: str | None = Field(
        default=None,
        min_length=1,
        description="Model name for this subagent (None = inherit from parent agent)",
    )
    skills: list[str] | None = Field(
        default=None,
        description=(
            "Skill names whitelist for this subagent. None inherits all enabled skills; "
            "[] means no skills are loaded."
        ),
    )


class CustomSubagentConfig(BaseModel):
    """A user-defined subagent type declared in configuration."""

    description: str = Field(description="When the lead agent should delegate to this subagent")
    system_prompt: str = Field(
        description="System prompt that guides the subagent's behavior",
    )
    tools: list[str] | None = Field(
        default=None,
        description="Tool names whitelist (None = inherit all tools from parent)",
    )
    disallowed_tools: list[str] = Field(
        default_factory=lambda: ["task", "ask_clarification", "present_files"],
        description="Tool names to deny",
    )
    skills: list[str] | None = Field(
        default=None,
        description="Skill names whitelist (None = inherit, [] = no skills)",
    )
    model: str = Field(
        default="inherit",
        description="Model to use — 'inherit' uses parent's model",
    )
    max_turns: int = Field(default=50, ge=1, description="Max turns before stopping")
    timeout_seconds: int = Field(default=900, ge=1, description="Max execution time in seconds")


class SubagentsAppConfig(BaseModel):
    """Top-level subagent settings.

    Defaults match deer-flow: ``timeout_seconds=1800`` (30 min global cap),
    ``max_turns=None`` (use builtin default per agent type).
    """

    timeout_seconds: int = Field(
        default=1800,
        ge=1,
        description=(
            "Default timeout in seconds for built-in subagents (1800 = 30 min). "
            "Custom agents use their own timeout_seconds unless overridden via agents[name]."
        ),
    )
    max_turns: int | None = Field(
        default=None,
        ge=1,
        description="Optional default max-turn override (None = keep builtin defaults)",
    )
    agents: dict[str, SubagentOverrideConfig] = Field(
        default_factory=dict,
        description="Per-agent override configuration keyed by agent name",
    )
    custom_agents: dict[str, CustomSubagentConfig] = Field(
        default_factory=dict,
        description="User-defined subagent types keyed by agent name",
    )

    def get_timeout_for(self, agent_name: str) -> int:
        """Effective timeout for ``agent_name`` after layer resolution."""
        override = self.agents.get(agent_name)
        if override is not None and override.timeout_seconds is not None:
            return override.timeout_seconds
        return self.timeout_seconds

    def get_model_for(self, agent_name: str) -> str | None:
        """Per-agent model override (None = inherit from parent)."""
        override = self.agents.get(agent_name)
        if override is not None and override.model is not None:
            return override.model
        return None

    def get_max_turns_for(self, agent_name: str, builtin_default: int) -> int:
        """Effective max_turns for ``agent_name`` after layer resolution."""
        override = self.agents.get(agent_name)
        if override is not None and override.max_turns is not None:
            return override.max_turns
        if self.max_turns is not None:
            return self.max_turns
        return builtin_default

    def get_skills_for(self, agent_name: str) -> list[str] | None:
        """Per-agent skills whitelist (None = inherit all enabled skills)."""
        override = self.agents.get(agent_name)
        if override is not None and override.skills is not None:
            return override.skills
        return None


__all__ = [
    "CustomSubagentConfig",
    "SubagentOverrideConfig",
    "SubagentsAppConfig",
]
