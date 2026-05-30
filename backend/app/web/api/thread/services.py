"""services — start_run, sse_consumer, format_sse, normalize_input."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID

from fastapi import HTTPException, Request
from langchain_core.messages import convert_to_messages
from langchain_core.messages.base import BaseMessage
from langchain_core.runnables import RunnableConfig

from app.common.runs.manager import ConflictError, RunManager
from app.common.runs.schemas import DisconnectMode
from app.common.stream_bridge.base import StreamBridge
from app.core.chat.service.thread_service import ThreadService
from app.core.chat.service.worker import run_agent

logger = logging.getLogger(__name__)

_DEFAULT_ASSISTANT_ID = "lead_agent"

# Config keys injectable via request context
_CONTEXT_CONFIGURABLE_KEYS = frozenset(
    {
        "model_name",
        "thinking_enabled",
        "reasoning_effort",
        "is_plan_mode",
        "subagent_enabled",
        "max_concurrent_subagents",
        "agent_name",
        "is_bootstrap",
    }
)

# Input validation constants
MAX_MESSAGE_LENGTH = 32768  # 32KB per message
ALLOWED_ROLES = frozenset({"user", "assistant", "system", "tool"})


def format_sse(event: str, data: Any, *, event_id: str | None = None) -> str:
    """Format a single SSE frame."""
    lines = [f"event: {event}"]
    data_str = json.dumps(data, ensure_ascii=False, default=str) if data is not None else "null"
    lines.append(f"data: {data_str}")
    if event_id is not None:
        lines.append(f"id: {event_id}")
    lines.append("")
    lines.append("")
    return "\n".join(lines)


def normalize_input(raw_input: dict[str, Any]) -> dict[str, Any]:
    """Convert input messages to LangChain format with validation.

    - Converts dict messages to BaseMessage instances
    - Validates message length (max 32KB)
    - Validates role whitelist

    Raises:
        HTTPException(400) on invalid input (sanitized message).
    """
    messages = raw_input.get("messages", [])
    if not messages:
        return {"messages": []}

    converted = []
    for i, msg in enumerate(messages):
        if isinstance(msg, BaseMessage):
            converted.append(msg)
        elif isinstance(msg, dict):
            # Validate role
            role = msg.get("role", "")
            if role and role not in ALLOWED_ROLES:
                logger.warning("Invalid role '%s' at message index %d", role, i)
                raise HTTPException(
                    status_code=400,
                    detail="请求参数无效",
                )
            # Validate length
            content = msg.get("content", "")
            if isinstance(content, str) and len(content) > MAX_MESSAGE_LENGTH:
                logger.warning(
                    "Message at index %d exceeds %d chars", i, MAX_MESSAGE_LENGTH
                )
                raise HTTPException(
                    status_code=400,
                    detail="请求参数无效",
                )
            try:
                converted.extend(convert_to_messages([msg]))
            except Exception as e:
                logger.warning("Invalid message at index %d: %s", i, e)
                raise HTTPException(
                    status_code=400,
                    detail="请求参数无效",
                )
        else:
            logger.warning(
                "Unsupported message type at index %d: %s", i, type(msg)
            )
            raise HTTPException(
                status_code=400,
                detail="请求参数无效",
            )
    return {"messages": converted}


def build_run_config(
    thread_id: UUID,
    request_config: dict[str, Any],
    metadata: dict[str, Any],
    *,
    assistant_id: str = _DEFAULT_ASSISTANT_ID,
) -> RunnableConfig:
    """Build RunnableConfig from request parameters."""
    configurable: dict[str, Any] = {"thread_id": thread_id}

    for key in _CONTEXT_CONFIGURABLE_KEYS:
        if key in request_config:
            configurable[key] = request_config[key]

    if assistant_id != _DEFAULT_ASSISTANT_ID:
        configurable["agent_name"] = assistant_id

    return RunnableConfig(
        configurable=configurable,
        metadata=metadata,
    )


def merge_run_context_overrides(
    config: RunnableConfig,
    context: dict[str, Any],
) -> RunnableConfig:
    """Merge request context into configurable."""
    configurable = dict(config.get("configurable", {}))
    for key in _CONTEXT_CONFIGURABLE_KEYS:
        if key in context:
            configurable[key] = context[key]
    return RunnableConfig(
        configurable=configurable,
        metadata=config.get("metadata") or {},
    )


def normalize_stream_modes(stream_mode: Any) -> list[str]:
    """Normalize stream_mode to a list of strings.

    Handles None, str, and list inputs.
    """
    if stream_mode is None:
        return ["values"]
    if isinstance(stream_mode, str):
        return [stream_mode]
    if isinstance(stream_mode, list):
        return stream_mode
    return ["values"]


def inject_authenticated_user_context(
    config: RunnableConfig,
    user_id: UUID,
) -> RunnableConfig:
    """Inject authenticated user_id into runnable config."""
    configurable = dict(config.get("configurable", {}))
    configurable["user_id"] = user_id
    return RunnableConfig(configurable=configurable, metadata=config.get("metadata") or {})


def resolve_agent_factory(assistant_id: str | None) -> Any:
    """Resolve agent factory based on assistant_id.

    Currently returns make_lead_agent. In the future this would
    support multiple agent types based on assistant_id.
    """
    from app.core.chat.agent.lead_agent import make_lead_agent

    return make_lead_agent


async def start_run(
    bridge: StreamBridge,
    run_manager: RunManager,
    thread_service: ThreadService,
    checkpointer: Any,
    body: Any,
    thread_id: UUID,
    request: Request,
    agent_factory: Any,
) -> Any:
    """Create and start a run.

    Flow:
    1. RunManager.create_or_reject (concurrency control)
    2. ThreadService.create (ensure thread exists)
    3. normalize_input (message format conversion)
    4. build_run_config (RunnableConfig construction)
    5. asyncio.create_task(run_agent(...))
    """
    # 1. Extract assistant_id and model name
    assistant_id = getattr(body, "assistant_id", None) or _DEFAULT_ASSISTANT_ID
    context = getattr(body, "context", {}) or {}
    model_name = context.get("model_name")

    # 2. Create run with concurrency control
    try:
        record = await run_manager.create_or_reject(
            thread_id=thread_id,
            user_id=request.state.current_user_id,
            model_name=model_name,
            assistant_id=assistant_id,
            multitask_strategy=getattr(body, "multitask_strategy", "reject"),
            on_disconnect=DisconnectMode(getattr(body, "on_disconnect", "cancel")),
            metadata=getattr(body, "metadata", None),
        )
    except ConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))

    # 3. Ensure thread exists
    await thread_service.create(
        thread_id=thread_id,
        user_id=request.state.current_user_id,
        model_name=model_name,
    )

    # 4. Normalize input
    raw_input = getattr(body, "input", {"messages": []})
    graph_input = normalize_input(raw_input)

    # 5. Build config
    request_config = getattr(body, "config", {}) or {}
    metadata = getattr(body, "metadata", {}) or {}
    config = build_run_config(thread_id, request_config, metadata, assistant_id=assistant_id)

    # 6. Merge context
    config = merge_run_context_overrides(config, context)

    # 7. Inject user_id via helper
    config = inject_authenticated_user_context(config, request.state.current_user_id)

    # 8. Inject checkpointer and additional config
    configurable = dict(config.get("configurable", {}))
    configurable["checkpointer"] = checkpointer
    # Pass through interrupt/configure options
    if getattr(body, "interrupt_before", None):
        configurable["interrupt_before"] = body.interrupt_before
    if getattr(body, "interrupt_after", None):
        configurable["interrupt_after"] = body.interrupt_after
    if getattr(body, "stream_subgraphs", False):
        configurable["stream_subgraphs"] = True
    config = RunnableConfig(configurable=configurable, metadata=config.get("metadata") or {})

    # 9. Resolve agent factory and build agent
    resolved_factory = resolve_agent_factory(assistant_id)
    agent = resolved_factory(config=config)

    task = asyncio.create_task(
        run_agent(
            bridge=bridge,
            run_manager=run_manager,
            record=record,
            agent=agent,
            graph_input=graph_input,
            config=config,
        ),
        name=f"run-{record.run_id}",
    )
    record.task = task

    return record


HEARTBEAT_SENTINEL = ": heartbeat\n\n"
END_SENTINEL = None


async def sse_consumer(
    bridge: StreamBridge,
    record: Any,
    request: Request,
    run_manager: RunManager,
) -> AsyncIterator[str]:
    """Consume StreamBridge events as SSE frames.

    Supports reconnection via Last-Event-ID header.
    Per-event disconnect detection to handle client disconnection promptly.
    """
    last_event_id = request.headers.get("Last-Event-ID")
    try:
        async for event in bridge.subscribe(
            record.run_id,
            last_event_id=last_event_id,
            heartbeat_interval=15.0,
        ):
            # Per-event disconnect check
            if await request.is_disconnected():
                logger.info("Client disconnected for run %s, cancelling", record.run_id)
                break

            if event.event == "__heartbeat__":
                yield HEARTBEAT_SENTINEL
                continue

            if event.event == "__end__":
                yield format_sse("end", None, event_id=event.id)
                break

            yield format_sse(event.event, event.data, event_id=event.id)

    except asyncio.CancelledError:
        logger.info("SSE client disconnected for run %s", record.run_id)
    finally:
        if record.on_disconnect == DisconnectMode.CANCEL:
            if record.status.value in ("pending", "running"):
                await run_manager.cancel(record.run_id)
