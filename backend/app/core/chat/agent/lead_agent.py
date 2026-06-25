"""Lead agent graph factory."""

from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode

from app.core.chat.agent.prompt import apply_prompt_template
from app.core.chat.agent.thread_state import ThreadState
from app.core.chat.middlewares.base import AgentMiddleware
from app.core.chat.middlewares.clarification_middleware import ClarificationMiddleware
from app.core.chat.middlewares.dc42_context_middleware import DC42ContextMiddleware
from app.core.chat.middlewares.dynamic_context_middleware import DynamicContextMiddleware
from app.core.chat.middlewares.loop_detection_middleware import LoopDetectionMiddleware
from app.core.chat.middlewares.memory_middleware import MemoryMiddleware
from app.core.chat.middlewares.subagent_limit_middleware import SubagentLimitMiddleware
from app.core.chat.middlewares.summarization_middleware import SummarizationMiddleware
from app.core.chat.middlewares.title_middleware import TitleMiddleware
from app.core.chat.middlewares.token_usage_middleware import TokenUsageMiddleware
from app.core.chat.tools.builtin.lint_tool import lint_code_tool
from app.core.chat.tools.builtin.param_tool import make_validate_parameters_tool
from app.core.jq_kb.tools import get_tools
from app.settings import get_settings

_SYSTEM_SUFFIX_MARKERS = ("[系统上下文]", "[DC42 Knowledge]", "<dc42_knowledge>", "<memory>")


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

    model = ChatOpenAI(
        model=model_name,
        api_key=settings.openai_api_key.get_secret_value(),
        base_url=settings.openai_base_url,
        streaming=True,
        extra_body={"reasoning_split": True},
    )

    # Tools — lint/validate + jq_kb (PR1: search_jq_api)
    tools: list[Any] = [
        lint_code_tool,
        make_validate_parameters_tool(),
        *get_tools(pr_phase=1),
    ]
    if tools:
        model = model.bind_tools(tools)

    # System prompt
    system_prompt = apply_prompt_template()

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

        messages = _ensure_system_message(messages, system_prompt)

        # LLM call
        response = await model.ainvoke(messages)

        # after_model hooks
        state_update: dict[str, Any] = {"messages": [response], **state_patches}
        preview_state = {**dict(state), **state_update}
        preview_state["messages"] = [
            *list(state.get("messages", [])),
            *state_update.get("messages", []),
        ]
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

    # Summarization enabled flag
    summarization_enabled = configurable.get("summarization_enabled", True)
    max_messages = configurable.get("max_messages", 50)
    dc42_retriever = configurable.get("dc42_retriever")

    return [
        TitleMiddleware(),
        TokenUsageMiddleware(),
        SummarizationMiddleware(max_messages=max_messages, enabled=summarization_enabled),
        DynamicContextMiddleware(),
        DC42ContextMiddleware(retriever=dc42_retriever),
        ClarificationMiddleware(),
        LoopDetectionMiddleware(),
        SubagentLimitMiddleware(),
        MemoryMiddleware(),
    ]
