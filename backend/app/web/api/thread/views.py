from __future__ import annotations

import contextlib
from typing import Annotated, Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

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
