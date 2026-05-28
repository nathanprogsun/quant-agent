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
from app.core.chat.middlewares.title_middleware import TitleMiddleware
from app.core.chat.middlewares.token_usage_middleware import TokenUsageMiddleware
from app.core.chat.middlewares.summarization_middleware import SummarizationMiddleware
from app.core.chat.middlewares.dynamic_context_middleware import DynamicContextMiddleware
from app.core.chat.middlewares.clarification_middleware import ClarificationMiddleware
from app.core.chat.middlewares.loop_detection_middleware import LoopDetectionMiddleware
from app.core.chat.middlewares.subagent_limit_middleware import SubagentLimitMiddleware
from app.core.chat.middlewares.memory_middleware import MemoryMiddleware
from app.settings import get_settings


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
    model_name = configurable.get("model_name", settings.llm_model)

    model = ChatOpenAI(
        model=model_name,
        api_key=settings.llm_api_key.get_secret_value(),
        base_url=settings.llm_api_base,
        streaming=True,
    )

    # Tools — TODO: Phase 1 empty, Phase 2+ loaded dynamically
    tools: list[Any] = []

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
        messages = list(state.get("messages", []))

        # Inject system prompt if not present
        if not messages or not isinstance(messages[0], SystemMessage):
            messages = [SystemMessage(content=system_prompt), *messages]

        # before_model hooks
        for mw in middlewares:
            modified = await mw.before_model(dict(state), {})
            if modified:
                messages = modified.get("messages", messages)

        # LLM call
        response = await model.ainvoke(messages)

        # after_model hooks
        state_update: dict[str, Any] = {"messages": [response]}
        for mw in middlewares:
            modified = await mw.after_model({**dict(state), **state_update}, {})
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

    return [
        TitleMiddleware(),
        TokenUsageMiddleware(),
        SummarizationMiddleware(max_messages=max_messages, enabled=summarization_enabled),
        DynamicContextMiddleware(),
        ClarificationMiddleware(),
        LoopDetectionMiddleware(),
        SubagentLimitMiddleware(),
        MemoryMiddleware(),
    ]
