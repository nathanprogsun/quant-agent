from __future__ import annotations

import contextlib
from typing import Annotated, Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from langgraph.checkpoint.base import RunnableConfig

from app.core.chat.agent.lead_agent import make_lead_agent
from app.core.chat.service.thread_service import ThreadService
from app.db.models.user import User
from app.web.api.deps import get_current_user
from app.web.api.thread.schema import (
    RunCreateRequest,
    RunListResponse,
    RunResponse,
    ThreadListResponse,
    ThreadResponse,
    ThreadTokenUsageResponse,
    UpdateTitleRequest,
)
from app.web.api.thread.services import sse_consumer, start_run
from app.web.lifespan_service import thread_service_from_lifespan

router = APIRouter(prefix="/api/v1/threads", tags=["threads"])


@router.get("", response_model=ThreadListResponse)
async def list_threads(
    current_user: Annotated[User, Depends(get_current_user)],
    thread_service: Annotated[ThreadService, Depends(thread_service_from_lifespan)],
    limit: int = 50,
    offset: int = 0,
) -> ThreadListResponse:
    """List threads for the current user."""
    threads = await thread_service.list_by_user_id(
        current_user.id, limit=limit, offset=offset
    )
    return ThreadListResponse(
        threads=[
            ThreadResponse(
                id=t.id,
                user_id=t.user_id,
                title=t.title,
                model_name=t.model_name,
                created_at=str(t.created_at) if t.created_at else None,
                updated_at=t.updated_at,
            )
            for t in threads
        ]
    )


@router.post("", response_model=ThreadResponse, status_code=201)
async def create_thread(
    current_user: Annotated[User, Depends(get_current_user)],
    thread_service: Annotated[ThreadService, Depends(thread_service_from_lifespan)],
    request: Request,
) -> ThreadResponse:
    """Create a new thread."""

    thread_id = uuid4()
    body: dict[str, Any] = {}
    with contextlib.suppress(Exception):
        body = await request.json()

    # Use provided thread_id if given (for LangGraph SDK compatibility)
    # SDK sends threadId (camelCase) but we also check thread_id (snake_case)
    provided_id = body.get("thread_id") or body.get("threadId")
    if provided_id:
        with contextlib.suppress(ValueError):
            thread_id = UUID(provided_id)

    thread = await thread_service.create(
        thread_id=thread_id,
        user_id=current_user.id,
        title=body.get("title"),
        model_name=body.get("model_name"),
    )
    return ThreadResponse(
        id=thread.id,
        user_id=thread.user_id,
        title=thread.title,
        model_name=thread.model_name,
        created_at=str(thread.created_at) if thread.created_at else None,
        updated_at=thread.updated_at,
    )


@router.get("/{thread_id}", response_model=ThreadResponse)
async def get_thread(
    thread_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    thread_service: Annotated[ThreadService, Depends(thread_service_from_lifespan)],
) -> ThreadResponse:
    """Get thread by ID."""
    thread = await thread_service.get(thread_id, current_user.id)
    return ThreadResponse(
        id=thread.id,
        user_id=thread.user_id,
        title=thread.title,
        model_name=thread.model_name,
        created_at=str(thread.created_at) if thread.created_at else None,
        updated_at=thread.updated_at,
    )


@router.patch("/{thread_id}", response_model=ThreadResponse)
async def update_thread(
    thread_id: UUID,
    body: UpdateTitleRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    thread_service: Annotated[ThreadService, Depends(thread_service_from_lifespan)],
) -> ThreadResponse:
    """Update thread title."""
    thread = await thread_service.update_title(thread_id, current_user.id, body.title)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    return ThreadResponse(
        id=thread.id,
        user_id=thread.user_id,
        title=thread.title,
        model_name=thread.model_name,
        created_at=str(thread.created_at) if thread.created_at else None,
        updated_at=thread.updated_at,
    )


@router.delete("/{thread_id}", status_code=204)
async def delete_thread(
    thread_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    thread_service: Annotated[ThreadService, Depends(thread_service_from_lifespan)],
) -> None:
    """Soft delete a thread."""
    deleted = await thread_service.delete(thread_id, current_user.id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Thread not found")


@router.get("/{thread_id}/runs", response_model=RunListResponse)
async def list_runs(
    thread_id: UUID,
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
) -> RunListResponse:
    """List all runs for a thread."""
    app_context = request.app.state.app_context
    if app_context.run_manager is None:
        raise HTTPException(status_code=503, detail="RunManager not available")
    records = await app_context.run_manager.list_by_thread(thread_id)
    return RunListResponse(runs=[RunResponse.from_run_record(r) for r in records])


@router.get("/{thread_id}/runs/{run_id}", response_model=RunResponse)
async def get_run(
    thread_id: UUID,
    run_id: UUID,
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
) -> RunResponse:
    """Get a specific run by ID."""
    app_context = request.app.state.app_context
    if app_context.run_manager is None:
        raise HTTPException(status_code=503, detail="RunManager not available")

    record = await app_context.run_manager.get(run_id)
    if not record or record.thread_id != thread_id:
        raise HTTPException(status_code=404, detail="Run not found")
    return RunResponse.from_run_record(record)


@router.post("/{thread_id}/runs", response_model=RunResponse, status_code=201)
async def create_run(
    thread_id: UUID,
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
) -> RunResponse:
    """Create a new run (non-streaming) - TODO: implement."""
    raise HTTPException(
        status_code=501, detail="Not implemented: use POST /api/v1/chat/stream instead"
    )


@router.post("/{thread_id}/runs/wait", response_model=RunResponse)
async def wait_for_run(
    thread_id: UUID,
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
) -> RunResponse:
    """Block and wait for a run to complete - TODO: implement."""
    raise HTTPException(status_code=501, detail="Not implemented")


@router.get("/{thread_id}/runs/{run_id}/join")
async def join_run(
    thread_id: UUID,
    run_id: UUID,
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
) -> StreamingResponse:
    """Join an existing run's SSE stream."""
    app_context = request.app.state.app_context
    if app_context.run_manager is None:
        raise HTTPException(status_code=503, detail="RunManager not available")

    record = await app_context.run_manager.get(run_id)
    if not record or record.thread_id != thread_id:
        raise HTTPException(status_code=404, detail="Run not found")

    return StreamingResponse(
        sse_consumer(
            bridge=app_context.stream_bridge,
            record=record,
            request=request,
            run_manager=app_context.run_manager,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/{thread_id}/runs/{run_id}/stream")
async def get_stream_run(
    thread_id: UUID,
    run_id: UUID,
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
) -> StreamingResponse:
    """Get or cancel+get SSE stream for an existing run."""
    action = request.query_params.get("action")

    app_context = request.app.state.app_context
    if app_context.run_manager is None:
        raise HTTPException(status_code=503, detail="RunManager not available")

    record = await app_context.run_manager.get(run_id)
    if not record or record.thread_id != thread_id:
        raise HTTPException(status_code=404, detail="Run not found")

    if action == "cancel":
        await app_context.run_manager.cancel(run_id)

    return StreamingResponse(
        sse_consumer(
            bridge=app_context.stream_bridge,
            record=record,
            request=request,
            run_manager=app_context.run_manager,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/{thread_id}/messages")
async def get_messages(
    thread_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    request: Request,
    limit: int = 50,
    before: int | None = None,
    after: int | None = None,
) -> dict[str, Any]:
    """Get messages for a thread with optional pagination."""
    app_context = request.app.state.app_context

    if not app_context.checkpointer:
        raise HTTPException(status_code=503, detail="Checkpointer not available")

    config = RunnableConfig(configurable={"thread_id": str(thread_id)})
    checkpoint = await app_context.checkpointer.aget(config)

    if not checkpoint or not checkpoint.channel_values.get("messages"):
        return {"messages": [], "total": 0}

    messages = checkpoint.channel_values["messages"]

    if before is not None:
        messages = [m for m in messages if m.get("seq", 0) < before]
    if after is not None:
        messages = [m for m in messages if m.get("seq", 0) > after]

    messages = messages[-limit:]
    return {"messages": messages, "total": len(messages)}


@router.get("/{thread_id}/runs/{run_id}/messages")
async def get_run_messages(
    thread_id: UUID,
    run_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    request: Request,
    limit: int = 50,
    before: int | None = None,
) -> dict[str, Any]:
    """Get messages for a specific run with pagination."""
    app_context = request.app.state.app_context

    record = await app_context.run_manager.get(run_id)
    if not record or record.thread_id != thread_id:
        raise HTTPException(status_code=404, detail="Run not found")

    if not app_context.checkpointer:
        return {"messages": [], "total": 0}

    config = RunnableConfig(configurable={"thread_id": str(thread_id), "run_id": str(run_id)})
    checkpoint = await app_context.checkpointer.aget(config)

    if not checkpoint or not checkpoint.channel_values.get("messages"):
        return {"messages": [], "total": 0}

    messages = checkpoint.channel_values["messages"]

    if before is not None:
        messages = [m for m in messages if m.get("seq", 0) < before]

    messages = messages[-limit:]
    return {"messages": messages, "total": len(messages)}


@router.get("/{thread_id}/runs/{run_id}/events")
async def get_events(
    thread_id: UUID,
    run_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    request: Request,
    event_types: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    """Get events for a run."""
    app_context = request.app.state.app_context

    record = await app_context.run_manager.get(run_id)
    if not record or record.thread_id != thread_id:
        raise HTTPException(status_code=404, detail="Run not found")

    parsed_types = event_types.split(",") if event_types else None

    events = []
    async for event in app_context.stream_bridge.subscribe(
        run_id,
        last_event_id=None,
        heartbeat_interval=15.0,
    ):
        if parsed_types is None or event.event in parsed_types:
            events.append({"event": event.event, "data": event.data, "id": event.id})
        if len(events) >= limit:
            break

    return {"events": events, "total": len(events)}


@router.get("/{thread_id}/token-usage", response_model=ThreadTokenUsageResponse)
async def get_token_usage(
    thread_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    request: Request,
) -> ThreadTokenUsageResponse:
    """Get aggregated token usage for a thread."""
    app_context = request.app.state.app_context
    if app_context.run_manager is None:
        raise HTTPException(status_code=503, detail="RunManager not available")

    records = await app_context.run_manager.list_by_thread(thread_id)

    total_input = 0
    total_output = 0
    total_tokens = 0
    llm_calls = 0
    lead_tokens = 0
    subagent_tokens = 0
    middleware_tokens = 0
    message_count = 0
    by_model: dict[str, dict[str, int]] = {}

    for record in records:
        total_input += getattr(record, "total_input_tokens", 0)
        total_output += getattr(record, "total_output_tokens", 0)
        total_tokens += getattr(record, "total_tokens", 0)
        llm_calls += getattr(record, "llm_call_count", 0)
        lead_tokens += getattr(record, "lead_agent_tokens", 0)
        subagent_tokens += getattr(record, "subagent_tokens", 0)
        middleware_tokens += getattr(record, "middleware_tokens", 0)
        message_count += getattr(record, "message_count", 0)

        model = record.model_name or "unknown"
        if model not in by_model:
            by_model[model] = {"total_input": 0, "total_output": 0, "total": 0, "calls": 0}
        by_model[model]["total_input"] += getattr(record, "total_input_tokens", 0)
        by_model[model]["total_output"] += getattr(record, "total_output_tokens", 0)
        by_model[model]["total"] += getattr(record, "total_tokens", 0)
        by_model[model]["calls"] += getattr(record, "llm_call_count", 0)

    return ThreadTokenUsageResponse(
        thread_id=thread_id,
        total_input_tokens=total_input,
        total_output_tokens=total_output,
        total_tokens=total_tokens,
        llm_call_count=llm_calls,
        lead_agent_tokens=lead_tokens,
        subagent_tokens=subagent_tokens,
        middleware_tokens=middleware_tokens,
        message_count=message_count,
        by_model=[
            {"model_name": m, "total_input_tokens": v["total_input"], "total_output_tokens": v["total_output"], "total_tokens": v["total"], "llm_call_count": v["calls"]}
            for m, v in by_model.items()
        ],
    )


@router.post("/{thread_id}/runs/stream")
async def stream_run(
    thread_id: UUID,
    body: RunCreateRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    thread_service: Annotated[ThreadService, Depends(thread_service_from_lifespan)],
    request: Request,
) -> StreamingResponse:
    """Create a run and stream events via SSE."""
    app_context = request.app.state.app_context

    record = await start_run(
        bridge=app_context.stream_bridge,
        run_manager=app_context.run_manager,
        thread_service=thread_service,
        checkpointer=app_context.checkpointer,
        body=body,
        thread_id=thread_id,
        request=request,
        agent_factory=make_lead_agent,
    )

    return StreamingResponse(
        sse_consumer(
            bridge=app_context.stream_bridge,
            record=record,
            request=request,
            run_manager=app_context.run_manager,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/{thread_id}/runs/{run_id}/cancel")
async def cancel_run(
    thread_id: UUID,
    run_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    request: Request,
) -> dict[str, Any]:
    """Cancel a running run."""
    app_context = request.app.state.app_context
    cancelled = await app_context.run_manager.cancel(run_id)
    if not cancelled:
        raise HTTPException(status_code=404, detail="Run not found or already finished")
    return {"status": "cancelled", "run_id": run_id}


@router.get("/{thread_id}/history")
async def get_thread_history(
    thread_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    request: Request,
) -> dict[str, Any]:
    """Get thread history from checkpointer."""
    app_context = request.app.state.app_context
    checkpointer = app_context.checkpointer

    if not checkpointer:
        return {"messages": []}

    config = RunnableConfig(configurable={"thread_id": str(thread_id)})
    checkpoint = await checkpointer.aget(config)

    if checkpoint and checkpoint.channel_values.get("messages"):
        messages = checkpoint.channel_values["messages"]
    else:
        messages = []

    return {"messages": messages}
