"""Lead agent graph factory."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from langchain_core.messages import AIMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode
from pydantic import SecretStr

from app.config.extensions_config import ExtensionsConfig
from app.core.chat.agent.model_call import ModelCallRequest
from app.core.chat.agent.prompt import apply_prompt_template
from app.core.chat.agent.thread_state import ThreadState
from app.core.chat.middlewares.base import AgentMiddleware
from app.core.chat.middlewares.clarification_middleware import ClarificationMiddleware
from app.core.chat.middlewares.dynamic_context_middleware import DynamicContextMiddleware
from app.core.chat.middlewares.loop_detection_middleware import LoopDetectionMiddleware
from app.core.chat.middlewares.memory_middleware import MemoryMiddleware
from app.core.chat.middlewares.skill_activation_middleware import SkillActivationMiddleware
from app.core.chat.middlewares.subagent_limit_middleware import SubagentLimitMiddleware
from app.core.chat.middlewares.summarization_middleware import SummarizationMiddleware
from app.core.chat.middlewares.title_middleware import TitleMiddleware
from app.core.chat.middlewares.token_usage_middleware import TokenUsageMiddleware
from app.core.chat.tools.builtin.lint_tool import lint_code_tool
from app.core.chat.tools.builtin.param_tool import make_validate_parameters_tool
from app.core.chat.tools.builtin.read_file_tool import ReadFileTool
from app.core.jq_kb.tools import get_tools
from app.settings import get_settings
from app.skills.storage.local_skill_storage import LocalSkillStorage

# P4.3: "<memory>" is no longer a system-prompt suffix — memory is injected by
# DynamicContextMiddleware (P4.2) as a separate HumanMessage, not appended to
# the system prompt.
_SYSTEM_SUFFIX_MARKERS = ("[系统上下文]",)


def _system_suffix(text: str) -> str:
    """Preserve middleware-appended blocks when refreshing the base system prompt."""
    for marker in _SYSTEM_SUFFIX_MARKERS:
        idx = text.find(marker)
        if idx != -1:
            return text[idx:]
    return ""


def _ensure_system_message(messages: list[Any], system_prompt: str) -> list[Any]:
    """Ensure the latest base system prompt is first, keeping injected context suffixes."""
    if not messages:
        return [SystemMessage(content=system_prompt)]

    if isinstance(messages[0], SystemMessage):
        content = messages[0].content
        text = content if isinstance(content, str) else str(content)
        suffix = _system_suffix(text)
        refreshed = list(messages)
        refreshed[0] = SystemMessage(content=system_prompt + suffix)
        return refreshed

    return [SystemMessage(content=system_prompt), *messages]


def make_lead_agent(config: RunnableConfig) -> Any:
    """Agent graph factory.

    Builds a CompiledStateGraph with:
    - agent_node: LLM call (with before_model / after_model hooks)
    - tool_node: tool execution (Phase 1 empty tools list)
    - conditional edge: tool_calls → tools, else → END

    Args:
        config: RunnableConfig with runtime parameters in configurable.

    Returns:
        CompiledStateGraph instance.
    """
    settings = get_settings()  # TODO: migrate to configurable injection
    configurable = config.get("configurable", {})

    # Model resolution: requested → config → global default
    model_name = configurable.get("model_name", settings.model)

    model: Any = ChatOpenAI(
        model=model_name,
        api_key=SecretStr(settings.openai_api_key.get_secret_value()),
        base_url=settings.openai_base_url,
        streaming=True,
        extra_body={"reasoning_split": True},
    )

    # Tools — lint/validate + jq_kb (PR3: search_jq_api + search_jq_dict + search_jq_strategy)
    tools: list[Any] = [
        lint_code_tool,
        make_validate_parameters_tool(),
        ReadFileTool(containers=[Path(settings.skills_root)]),
        *get_tools(pr_phase=3),
    ]
    if tools:
        model = model.bind_tools(tools)

    # System prompt
    enabled_skills = _collect_enabled_skills(
        skills_root=Path(settings.skills_root),
        extensions_config_path=Path(settings.extensions_config_path),
    )
    system_prompt = apply_prompt_template(
        skills=enabled_skills,
        container_base_path=str(Path(settings.skills_root).resolve()),
    )

    # Middleware chain — Phase 1 empty, Phase 2+ assembled
    middlewares = _build_middlewares(config)

    # Build StateGraph
    graph = StateGraph(ThreadState)

    graph.add_node("agent", _make_agent_node(model, system_prompt, middlewares))
    if tools:
        graph.add_node("tools", ToolNode(tools))
        graph.add_edge("tools", "agent")

    graph.set_entry_point("agent")
    graph.add_conditional_edges("agent", _should_use_tools)

    checkpointer = configurable.get("checkpointer")
    return graph.compile(checkpointer=checkpointer)


def _make_agent_node(
    model: ChatOpenAI,
    system_prompt: str,
    middlewares: list[AgentMiddleware],
) -> Any:
    """Create the agent node function.

    Extracted as a standalone function for testability.
    """

    async def agent_node(state: ThreadState) -> dict[str, Any]:
        messages = _ensure_system_message(list(state.get("messages", [])), system_prompt)
        working_state: dict[str, Any] = {**dict(state), "messages": messages}

        # before_model hooks — must see the system prompt so middlewares do not drop it
        state_patches: dict[str, Any] = {}
        for mw in middlewares:
            modified = await mw.before_model(working_state, {})
            if modified:
                for key, value in modified.items():
                    if key == "messages":
                        messages = value
                        working_state["messages"] = messages
                    else:
                        state_patches[key] = value

        # NOTE: do NOT call _ensure_system_message again here.
        # DynamicContextMiddleware performs an ID-swap (first HumanMessage ->
        # SystemMessage reminder + {id}__user). Re-running _ensure_system_message
        # would rebuild the SystemMessage and break the frozen-snapshot prefix
        # cache. System message identity is preserved from the entry-point call.

        # LLM call — wrapped by awrap_model_call hooks (P1.7 SkillActivation
        # injects a <slash_skill_activation> block when the last user message
        # starts with /<skill-name>). Default ABC impl is a no-op delegate, so
        # middlewares that do not override the hook are unaffected. The request
        # is mutable: a middleware may replace `messages` before delegating; we
        # read it back so any injection persists via the add_messages reducer.
        request = ModelCallRequest(messages=messages)

        async def _invoke_model(req: ModelCallRequest) -> Any:
            return await model.ainvoke(req.messages)

        response = await _run_awrap_model_call(middlewares, request, _invoke_model)
        messages = request.messages

        # D9: persist the patched message list. Returning [*messages, response]
        # lets the add_messages reducer replace-in-place by id (the swapped
        # SystemMessage) and append the new {id}__user message + response.
        # Without this the ID-swap is ephemeral and prefix-cache reuse across
        # turns is impossible. Idempotent because add_messages assigns ids to
        # all checkpointed messages.
        state_update: dict[str, Any] = {"messages": [*messages, response], **state_patches}
        preview_state = {**working_state, "messages": [*messages, response]}
        for mw in middlewares:
            modified = await mw.after_model(preview_state, {})
            if modified:
                state_update.update(modified)

        return state_update

    return agent_node


def _should_use_tools(state: ThreadState) -> str:
    """Conditional edge: route to tools or END."""
    messages = state.get("messages", [])
    if not messages:
        return END
    last_message = messages[-1]
    if isinstance(last_message, AIMessage) and last_message.tool_calls:
        return "tools"
    return END


def _build_middlewares(config: RunnableConfig) -> list[AgentMiddleware]:
    """Build middleware chain.

    Assembles middlewares in order per DeerFlow convention:
    1. TitleMiddleware - generates conversation title
    2. TokenUsageMiddleware - tracks token usage
    3. SummarizationMiddleware - handles long conversation summarization
    4. DynamicContextMiddleware - injects current datetime/timezone
    5. ClarificationMiddleware - detects clarification requests
    6. LoopDetectionMiddleware - detects repeated tool call patterns
    7. SubagentLimitMiddleware - limits concurrent subagent calls
    """
    configurable = config.get("configurable", {})
    settings = get_settings()

    # Summarization enabled flag
    summarization_enabled = configurable.get("summarization_enabled", True)
    max_messages = configurable.get("max_messages", 50)
    skills_root = configurable.get("skills_root", settings.skills_root)

    return [
        TitleMiddleware(),
        TokenUsageMiddleware(),
        SummarizationMiddleware(max_messages=max_messages, enabled=summarization_enabled),
        DynamicContextMiddleware(),
        ClarificationMiddleware(),
        LoopDetectionMiddleware(),
        SubagentLimitMiddleware(),
        MemoryMiddleware(max_messages=max_messages),
        SkillActivationMiddleware(storage=LocalSkillStorage(root=Path(skills_root))),
    ]


async def _run_awrap_model_call(
    middlewares: list[AgentMiddleware],
    request: ModelCallRequest,
    handler: Any,
) -> Any:
    """Chain awrap_model_call hooks around the model invocation.

    Middlewares are wrapped so that the FIRST in the list is outermost
    (mirrors before_model ordering). The default ABC implementation is a
    no-op delegate, so middlewares that do not override the hook are
    transparent.
    """
    wrapped = handler
    for mw in reversed(middlewares):
        wrapped = _bind_awrap(mw, wrapped)
    return await wrapped(request)


def _bind_awrap(mw: AgentMiddleware, next_handler: Any) -> Any:
    async def call(req: ModelCallRequest) -> Any:
        return await mw.awrap_model_call(req, next_handler)

    return call


def _collect_enabled_skills(
    *,
    skills_root: Path,
    extensions_config_path: Path,
) -> tuple[tuple[str, str], ...]:
    """Discover skills on disk and filter by the extensions toggle state.

    Returns a tuple of (name, description) pairs — metadata only, never body.
    Order is the lexical name order from LocalSkillStorage. When the
    extensions config is missing or malformed, every discovered skill is
    treated as enabled (opt-out toggle) so a fresh checkout still works.
    """
    try:
        config = ExtensionsConfig.from_file(extensions_config_path)
    except (FileNotFoundError, ValueError, json.JSONDecodeError):
        config = None

    storage = LocalSkillStorage(root=skills_root)
    skills = storage.load_skills()
    if config is None:
        return tuple((s.name, s.description) for s in skills)
    return tuple((s.name, s.description) for s in skills if config.is_skill_enabled(s.name))
