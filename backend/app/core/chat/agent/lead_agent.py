"""Lead agent graph factory."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from langchain.agents import create_agent
from langchain.agents.middleware import AgentMiddleware
from langchain_core.runnables import RunnableConfig
from pydantic import SecretStr

from app.config.extensions_config import ExtensionsConfig
from app.core.chat.agent.features import RuntimeFeatures
from app.core.chat.agent.middleware_chain import build_middlewares
from app.core.chat.agent.prompt import apply_prompt_template
from app.core.chat.agent.thread_state import ThreadState
from app.core.chat.llm.patched_chat import PatchedChat
from app.core.chat.tools.builtin.lint_tool import lint_code_tool
from app.core.chat.tools.builtin.param_tool import make_validate_parameters_tool
from app.core.chat.tools.builtin.read_file_tool import ReadFileTool
from app.core.jq_kb.tools import get_tools
from app.settings import get_settings
from app.skills.storage.local_skill_storage import LocalSkillStorage
from app.skills.tool_policy import filter_tools_by_skill_allowed_tools
from app.tools.builtins.tool_search import (
    assemble_deferred_tools,
    get_deferred_tools_prompt_section,
)


def make_lead_agent(
    config: RunnableConfig,
    mcp_tools: list[Any] | None = None,
    *,
    features: RuntimeFeatures | None = None,
    custom_middlewares: list[AgentMiddleware] | None = None,
) -> Any:
    """Agent graph factory.

    Delegates to ``langchain.agents.create_agent`` — the framework builds the
    internal ``StateGraph`` (model_node + optional tool_node + conditional
    routing) and constructs langchain-native ``ModelRequest`` instances at
    runtime.

    Args:
        config: RunnableConfig with runtime parameters in configurable.
        mcp_tools: Optional pre-fetched MCP tools. When omitted, falls back
            to ``get_cached_mcp_tools()``.
        features: Optional RuntimeFeatures override. When omitted, builds
            from ``config["configurable"]``.
        custom_middlewares: Optional list of custom middlewares to inject
            before SafetyFinishReasonMiddleware.
    """
    settings = get_settings()
    configurable = config.get("configurable", {})

    # ── Features ──────────────────────────────────────────────
    resolved_features = features or RuntimeFeatures.from_runnable_config(configurable)

    # ── Model ─────────────────────────────────────────────────
    model_name = configurable.get("model_name", settings.model)

    extra_body: dict[str, Any] = {"reasoning_split": True}
    if resolved_features.reasoning_effort:
        extra_body["reasoning_effort"] = resolved_features.reasoning_effort

    model: Any = PatchedChat(
        model=model_name,
        api_key=SecretStr(settings.openai_api_key.get_secret_value()),
        base_url=settings.openai_base_url,
        streaming=True,
        extra_body=extra_body,
    )

    # ── Tools ─────────────────────────────────────────────────
    base_tools: list[Any] = [
        lint_code_tool,
        make_validate_parameters_tool(),
        ReadFileTool(containers=[Path(settings.skills_root)]),
        *get_tools(pr_phase=3),
    ]

    if mcp_tools is None:
        try:
            from app.mcp import get_cached_mcp_tools

            mcp_tools = get_cached_mcp_tools()
        except Exception:
            mcp_tools = []
    base_tools.extend(mcp_tools)

    # ── Skill-based tool filtering ────────────────────────────
    storage = LocalSkillStorage(root=Path(settings.skills_root))
    all_skills = storage.load_skills()
    enabled_skills = [s for s in all_skills if s.enabled]
    base_tools = filter_tools_by_skill_allowed_tools(base_tools, enabled_skills)

    # ── Deferred tools ────────────────────────────────────────
    tool_search_enabled = bool(mcp_tools)
    tools, deferred_setup = assemble_deferred_tools(base_tools, enabled=tool_search_enabled)

    # ── Skills metadata for prompt ────────────────────────────
    try:
        config_file = ExtensionsConfig.from_file(Path(settings.extensions_config_path))
    except (FileNotFoundError, ValueError, json.JSONDecodeError):
        config_file = None

    visible_skills = [
        s for s in enabled_skills if config_file is None or config_file.is_skill_enabled(s.name)
    ]

    # ── System prompt ─────────────────────────────────────────
    system_prompt = apply_prompt_template(
        skills=tuple((s.name, s.description) for s in visible_skills),
        container_base_path=str(Path(settings.skills_root).resolve()),
    )
    if deferred_setup.deferred_names:
        system_prompt = (
            system_prompt
            + "\n\n"
            + get_deferred_tools_prompt_section(deferred_names=deferred_setup.deferred_names)
        )

    # ── Middleware chain ──────────────────────────────────────
    available_skill_names = {s.name for s in visible_skills} if visible_skills else None

    middlewares = build_middlewares(
        config,
        features=resolved_features,
        available_skills=available_skill_names,
        skills_root=settings.skills_root,
        deferred_setup=deferred_setup,
        custom_middlewares=custom_middlewares,
    )

    # ── Build graph ───────────────────────────────────────────
    checkpointer = configurable.get("checkpointer")
    return create_agent(
        model=model,
        tools=tools,
        middleware=middlewares,
        system_prompt=system_prompt,
        state_schema=ThreadState,  # type: ignore[arg-type]
        checkpointer=checkpointer,
    )


async def make_lead_agent_async(config: RunnableConfig) -> Any:
    """Async agent graph factory — fetches MCP tools without blocking the loop."""
    from app.mcp.cache import get_cached_mcp_tools_async

    mcp_tools = await get_cached_mcp_tools_async()
    return make_lead_agent(config, mcp_tools=mcp_tools)
