"""Background worker — run_agent() executes LangGraph agent."""

from __future__ import annotations

import asyncio
import logging
from types import SimpleNamespace
from typing import Any
from uuid import UUID

from langchain_core.runnables import Runnable, RunnableConfig

from app.common.runs.manager import RunManager, RunRecord
from app.common.runs.schemas import RunStatus
from app.common.serialization import serialize
from app.common.stream_bridge.base import StreamBridge
from app.core.chat.service.stream_modes import resolve_langgraph_stream_modes
from app.core.chat.service.thread_service import ThreadService
from app.core.chat.service.types import GraphInput

logger = logging.getLogger(__name__)

STREAM_CLEANUP_DELAY_SECONDS = 1
RUN_CLEANUP_DELAY_SECONDS = 300
RUN_AGENT_TIMEOUT_SECONDS = 600


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
    logger.info("run_agent started for run %s (thread %s)", run_id, thread_id)

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

        # 3. Stream execution with timeout
        configurable = config.get("configurable", {})
        runtime_ctx = SimpleNamespace(
            thread_id=str(thread_id),
            user_id=configurable.get("user_id"),
            run_id=str(run_id),
        )

        async def _stream_chunks() -> None:
            # Single-mode fast path: astream yields raw chunks (no
            # ``(mode, data)`` wrapper), so skip the unpack step entirely
            # and publish directly. Multi-mode yields tuples and goes
            # through ``_unpack_stream_item``.
            if len(langgraph_modes) == 1:
                single_mode = langgraph_modes[0]
                async for chunk in agent.astream(
                    payload,
                    config=config,
                    stream_mode=single_mode,
                    context=runtime_ctx,
                ):
                    if record.abort_event.is_set():
                        logger.info("Run %s aborted", run_id)
                        break
                    event_name, serialized = _prepare_publish_payload(single_mode, chunk)
                    await bridge.publish(run_id, event_name, serialized)
                return

            async for chunk in agent.astream(
                payload,
                config=config,
                stream_mode=langgraph_modes,
                context=runtime_ctx,
            ):
                # Check abort
                if record.abort_event.is_set():
                    logger.info("Run %s aborted", run_id)
                    break
                mode, data = _unpack_stream_item(chunk, langgraph_modes)
                event_name, serialized = _prepare_publish_payload(mode, data)
                await bridge.publish(run_id, event_name, serialized)

        await asyncio.wait_for(_stream_chunks(), timeout=RUN_AGENT_TIMEOUT_SECONDS)

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
        logger.info("run_agent cancelled for run %s", run_id)
        # Force-save LangGraph checkpoint so the frontend can retrieve
        # partial messages after re-fetch. Without this, the streaming
        # content is lost when the user clicks "stop".
        try:
            current_state = await asyncio.wait_for(
                agent.aget_state(config),  # type: ignore[attr-defined]
                timeout=5.0,
            )
            if current_state and current_state.values:
                await asyncio.wait_for(
                    agent.aupdate_state(config, current_state.values),  # type: ignore[attr-defined]
                    timeout=5.0,
                )
        except (TimeoutError, asyncio.CancelledError):
            logger.warning("Checkpoint save timed out for run %s", run_id)
        except Exception:
            pass
        await run_manager.set_status(run_id, RunStatus.INTERRUPTED)
    except Exception as e:
        logger.exception("Run %s failed", run_id)
        await run_manager.set_status(run_id, RunStatus.ERROR, error=str(e))
        await bridge.publish(run_id, "error", {"message": "处理请求时出错，请稍后重试"})
    finally:
        logger.info("run_agent finally block for run %s", run_id)
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
        logger.info("run_agent cleanup tasks created for run %s", run_id)


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

        state = await asyncio.wait_for(agent.aget_state(config), timeout=5.0)
        title = (state.values or {}).get("title")
        if isinstance(title, str) and title.strip():
            await thread_service.update_title_or_raise(thread_id, user_id, title.strip())
    except (TimeoutError, asyncio.CancelledError):
        logger.warning("Title sync timed out for thread %s", thread_id)
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
    """Convert LangGraph stream chunks into SSE-compatible payloads.

    Mode-specific handling:

    - ``custom`` — carries ``get_stream_writer()`` emissions from the
      agent nodes (per-chunk model streaming). When the payload is a dict
      with a ``messages`` list, the first message is surfaced as an SSE
      ``messages`` event with ``[chunk_dump, {}]`` shape so the frontend
      sees incremental stream data instead of waiting for the full
      response. Otherwise the whole payload is serialized as the chunk.
    - ``messages`` — obj is ``(message_chunk, metadata_dict)``; returns
      ``[chunk_dump, metadata_dict]``.
    - ``values`` — obj is the full state dict; strips ``__pregel_*`` keys
      and base64 ``data:`` image blocks from ``hide_from_ui`` messages so
      they never reach the SSE wire.
    - everything else — recursive ``model_dump()`` / ``dict()`` fallback.

    The wire shapes are pinned by ``tests/unit/chat/test_worker_payload.py``
    and the SSE contract test; do not drift them without updating both.
    """
    if mode == "custom":
        # ``custom`` carries ``get_stream_writer()`` emissions from the
        # agent nodes (per-chunk model streaming). When the payload is a
        # dict with a ``messages`` list, surface the first message as a
        # ``messages`` event so the frontend sees incremental stream data;
        # otherwise serialize the whole payload as the chunk. The metadata
        # slot is always {} — custom emissions carry no per-chunk metadata.
        if isinstance(data, dict):
            msgs = data.get("messages")
            target = msgs[0] if isinstance(msgs, list) and msgs else data
        else:
            target = data
        return "messages", [serialize(target), {}]

    if mode == "messages":
        # Delegate to the mode-aware serializer: it handles the
        # ``(chunk, metadata)`` tuple, the 2-list shape, and the non-tuple
        # message-chunk fallback (model_dump). Keeping the tuple/list
        # branching out of the worker avoids duplicating
        # ``serialize_messages_tuple`` here.
        return "messages", serialize(data, mode="messages")

    event_name = mode
    if mode == "values":
        # delegate to the mode-aware serializer so channel values get
        # __pregel_* stripping + hide_from_ui image-block stripping.
        return event_name, serialize(data, mode="values")

    return event_name, serialize(data)
