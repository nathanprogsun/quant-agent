"""Background worker — run_agent() executes LangGraph agent."""

from __future__ import annotations

import asyncio
import logging
from typing import Any
from uuid import UUID

from langchain_core.runnables import Runnable, RunnableConfig

from app.common.runs.manager import RunManager, RunRecord
from app.common.runs.schemas import RunStatus
from app.common.stream_bridge.base import StreamBridge
from app.core.chat.service.stream_modes import resolve_langgraph_stream_modes
from app.core.chat.service.thread_service import ThreadService
from app.core.chat.service.types import GraphInput

logger = logging.getLogger(__name__)

STREAM_CLEANUP_DELAY_SECONDS = 60
RUN_CLEANUP_DELAY_SECONDS = 300


async def run_agent(
    bridge: StreamBridge,
    run_manager: RunManager,
    record: RunRecord,
    *,
    agent: Runnable[Any, Any],
    graph_input: GraphInput,
    config: RunnableConfig,
    stream_modes: list[str] | None = None,
    thread_service: ThreadService | None = None,
    user_id: UUID | None = None,
) -> None:
    """Execute agent in background, publishing events to StreamBridge.

    Lifecycle:
    1. Set status to running
    2. Publish metadata event
    3. astream() — publish each chunk to bridge
    4. Completion handling
    5. publish_end + cleanup
    """
    run_id = record.run_id
    thread_id = record.thread_id

    requested_modes = stream_modes
    langgraph_modes = resolve_langgraph_stream_modes(requested_modes)

    # Convert GraphInput to dict for LangGraph internal use
    payload = graph_input.model_dump()

    try:
        # 1. Set status
        await run_manager.set_status(run_id, RunStatus.RUNNING)

        # 2. Publish metadata
        await bridge.publish(
            run_id,
            "metadata",
            {
                "run_id": run_id,
                "thread_id": thread_id,
            },
        )

        # 3. Stream execution
        async for chunk in agent.astream(
            payload,
            config=config,
            stream_mode=langgraph_modes,
        ):
            # Check abort
            if record.abort_event.is_set():
                logger.info("Run %s aborted", run_id)
                break
            mode, data = _unpack_stream_item(chunk, langgraph_modes)
            event_name, serialized = _prepare_publish_payload(mode, data)
            await bridge.publish(run_id, event_name, serialized)

        # 4. Completion
        if record.abort_event.is_set():
            await run_manager.set_status(run_id, RunStatus.INTERRUPTED)
        else:
            await run_manager.set_status(run_id, RunStatus.SUCCESS)
            await _sync_thread_title_from_state(
                agent,
                config,
                thread_service,
                thread_id,
                user_id,
            )

    except asyncio.CancelledError:
        await run_manager.set_status(run_id, RunStatus.INTERRUPTED)
    except Exception as e:
        logger.exception("Run %s failed", run_id)
        await run_manager.set_status(run_id, RunStatus.ERROR, error=str(e))
        await bridge.publish(run_id, "error", {"message": "处理请求时出错，请稍后重试"})
    finally:
        try:
            await bridge.publish_end(run_id)
        except Exception:
            logger.exception("Failed to publish end event for run %s", run_id)

        _bridge_cleanup = asyncio.create_task(
            bridge.cleanup(run_id, delay=STREAM_CLEANUP_DELAY_SECONDS)
        )
        _run_cleanup = asyncio.create_task(
            run_manager.cleanup(run_id, delay=RUN_CLEANUP_DELAY_SECONDS)
        )


async def _sync_thread_title_from_state(
    agent: Any,
    config: RunnableConfig,
    thread_service: ThreadService | None,
    thread_id: UUID,
    user_id: UUID | None,
) -> None:
    """Persist graph state title to the thread row when still untitled."""
    if thread_service is None or user_id is None:
        return

    try:
        thread = await thread_service.get(thread_id, user_id)
        if thread.title:
            return

        state = await agent.aget_state(config)
        title = (state.values or {}).get("title")
        if isinstance(title, str) and title.strip():
            await thread_service.update_title_or_raise(
                thread_id, user_id, title.strip()
            )
    except Exception:
        logger.exception("Failed to sync title for thread %s", thread_id)


def _unpack_stream_item(
    item: Any,
    stream_modes: list[str],
) -> tuple[str, Any]:
    """Parse LangGraph astream output into (mode, data)."""
    if isinstance(item, tuple):
        if len(item) == 3:
            _, mode, data = item
            if mode in stream_modes:
                return mode, data
        elif len(item) == 2:
            mode, data = item
            if mode in stream_modes:
                return mode, data
    return "values", item


def _prepare_publish_payload(mode: str, data: Any) -> tuple[str, Any]:
    """Convert LangGraph stream chunks into SSE-compatible payloads."""
    event_name = "messages" if mode == "messages" else mode

    if mode == "messages":
        if isinstance(data, tuple) and len(data) == 2:
            chunk, metadata = data
            return event_name, [
                _serialize_chunk_data(chunk),
                _serialize_chunk_data(metadata) or {},
            ]
        if isinstance(data, list) and len(data) == 2:
            return event_name, [
                _serialize_chunk_data(data[0]),
                _serialize_chunk_data(data[1]) or {},
            ]

    return event_name, _serialize_chunk_data(data)


def _serialize_chunk_data(data: Any) -> Any:
    """Serialize LangGraph chunk data to JSON-compatible format.

    LangChain messages and LangGraph state dicts may contain
    non-serializable objects. This converts them to plain dicts.
    """
    if data is None:
        return None
    if isinstance(data, (str, int, float, bool)):
        return data
    if isinstance(data, dict):
        return {k: _serialize_chunk_data(v) for k, v in data.items()}
    if isinstance(data, list):
        return [_serialize_chunk_data(item) for item in data]
    if isinstance(data, tuple):
        return [_serialize_chunk_data(item) for item in data]
    # LangChain message objects have .dict() or model_dump()
    if hasattr(data, "model_dump"):
        return data.model_dump()
    if hasattr(data, "dict"):
        return data.dict()
    return str(data)
