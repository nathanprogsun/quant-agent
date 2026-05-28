from __future__ import annotations

import contextlib
from typing import Annotated, Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from langgraph.checkpoint.base import RunnableConfig
from pydantic import BaseModel

from app.common.runs.manager import RunManager
from app.common.runs.schemas import RunStatus
from app.core.chat.service.thread_service import ThreadService
from app.db.models.user import User
from app.web.api.deps import get_current_user
from app.web.lifespan_service import thread_service_from_lifespan

router = APIRouter(prefix="/api/v1/threads", tags=["threads"])


# ── Request / Response models ────────────────────────────────


class ThreadResponse(BaseModel):
    id: UUID
    user_id: UUID
    title: str | None = None
    model_name: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class ThreadListResponse(BaseModel):
    threads: list[ThreadResponse]


class UpdateTitleRequest(BaseModel):
    title: str


# ── Run response models ────────────────────────────────────────


class RunResponse(BaseModel):
    run_id: UUID
    thread_id: UUID
    user_id: UUID
    status: RunStatus
    model_name: str | None = None
    assistant_id: str | None = None
    metadata: dict[str, Any] = {}
    on_disconnect: str | None = None
    multitask_strategy: str | None = None
    error: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class RunListResponse(BaseModel):
    runs: list[RunResponse]


# ── Routes ───────────────────────────────────────────────────


@router.get("", response_model=ThreadListResponse)
async def list_threads(
    current_user: Annotated[User, Depends(get_current_user)],
    thread_service: Annotated[ThreadService, Depends(thread_service_from_lifespan)],
    limit: int = 50,
    offset: int = 0,
) -> ThreadListResponse:
    """List threads for the current user."""
    threads = await thread_service.list_by_user_id(current_user.id, limit=limit, offset=offset)
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

    thread = await thread_service.create_or_update(
        thread_id=thread_id,
        user_id=current_user.id,
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


# ── Run management routes ──────────────────────────────────────
# Nested under /api/v1/threads/{thread_id}/runs


def _get_run_manager(request: Request) -> RunManager:
    """Extract RunManager from app context."""
    app_context = request.app.state.app_context
    if app_context.run_manager is None:
        raise HTTPException(status_code=503, detail="RunManager not available")
    return app_context.run_manager


def _run_to_response(record) -> RunResponse:
    """Convert RunRecord to RunResponse."""
    return RunResponse(
        run_id=record.run_id,
        thread_id=record.thread_id,
        user_id=record.user_id,
        status=record.status,
        model_name=record.model_name,
        assistant_id=record.assistant_id,
        metadata=record.metadata,
        on_disconnect=record.on_disconnect.value if record.on_disconnect else None,
        multitask_strategy=record.multitask_strategy,
        error=record.error,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


@router.get("/{thread_id}/runs", response_model=RunListResponse)
async def list_runs(
    thread_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    run_manager: Annotated[RunManager, Depends(_get_run_manager)],
) -> RunListResponse:
    """List all runs for a thread."""
    records = await run_manager.list_by_thread(thread_id)
    return RunListResponse(runs=[_run_to_response(r) for r in records])


@router.get("/{thread_id}/runs/{run_id}", response_model=RunResponse)
async def get_run(
    thread_id: UUID,
    run_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    run_manager: Annotated[RunManager, Depends(_get_run_manager)],
) -> RunResponse:
    """Get a specific run by ID."""
    record = await run_manager.get(run_id)
    if not record or record.thread_id != thread_id:
        raise HTTPException(status_code=404, detail="Run not found")
    return _run_to_response(record)


@router.post("/{thread_id}/runs", response_model=RunResponse, status_code=201)
async def create_run(
    thread_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    run_manager: Annotated[RunManager, Depends(_get_run_manager)],
) -> RunResponse:
    """Create a new run (non-streaming) - TODO: implement."""
    raise HTTPException(status_code=501, detail="Not implemented: use POST /api/v1/chat/stream instead")


@router.post("/{thread_id}/runs/wait", response_model=RunResponse)
async def wait_for_run(
    thread_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    run_manager: Annotated[RunManager, Depends(_get_run_manager)],
) -> RunResponse:
    """Block and wait for a run to complete - TODO: implement."""
    raise HTTPException(status_code=501, detail="Not implemented")


@router.get("/{thread_id}/runs/{run_id}/join")
async def join_run(
    thread_id: UUID,
    run_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    run_manager: Annotated[RunManager, Depends(_get_run_manager)],
):
    """Join an existing run's SSE stream - TODO: implement."""
    raise HTTPException(status_code=501, detail="Not implemented")


# ── History route ──────────────────────────────────────────────


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
