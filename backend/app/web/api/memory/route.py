"""Memory API routes."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field

from app.core.chat.memory.service import MemoryService
from app.core.user.types import UserDTO
from app.web.api.deps import get_current_user
from app.web.lifespan_service import memory_service_from_request

router = APIRouter(prefix="/api/memory", tags=["memory"])


# ── Request models ───────────────────────────────────────────


class MemoryCreateRequest(BaseModel):
    """Request to create a user memory."""

    memory_type: str = Field(..., description="Type of memory (preference, fact, context, goal)")
    content: str = Field(..., max_length=4096, description="Memory content")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Confidence score 0-1")
    source: str | None = Field(default=None, description="Source of memory (chat, profile, explicit)")


class FactCreateRequest(BaseModel):
    """Request to create a memory fact."""

    fact_type: str = Field(..., description="Type of fact (preference, knowledge, plan, relationship)")
    content: str = Field(..., max_length=4096, description="Fact content")
    embedding: list[float] | None = Field(default=None, description="Vector embedding for similarity")


# ── Response models (DTOs, decoupled from DB TableModel) ──────


class UserMemoryOut(BaseModel):
    """Response DTO for a user memory record."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    memory_type: str
    content: str
    confidence: float
    source: str | None
    created_at: datetime
    updated_at: datetime | None


class MemoryFactOut(BaseModel):
    """Response DTO for a memory fact record."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    fact_type: str
    content: str
    embedding: list[float] | None
    created_at: datetime
    updated_at: datetime | None


class MemoryContextResponse(BaseModel):
    """Response containing user memory context."""

    memories: list[UserMemoryOut]
    facts: list[MemoryFactOut]
    context_string: str = Field(description="Formatted context string for prompts")


# ── Routes ───────────────────────────────────────────────────


@router.get("", response_model=MemoryContextResponse)
async def get_memory_context(
    current_user: Annotated[UserDTO, Depends(get_current_user)],
    memory_service: Annotated[MemoryService, Depends(memory_service_from_request)],
) -> MemoryContextResponse:
    """Get aggregated memory context for the current user.

    Returns all user memories and facts formatted for prompt injection.
    """
    context = await memory_service.get_user_memory(current_user.id)
    return MemoryContextResponse(
        memories=[UserMemoryOut.model_validate(m) for m in context.memories],
        facts=[MemoryFactOut.model_validate(f) for f in context.facts],
        context_string=context.to_prompt_string(),
    )


@router.post("/memories", response_model=UserMemoryOut)
async def create_memory(
    body: MemoryCreateRequest,
    current_user: Annotated[UserDTO, Depends(get_current_user)],
    memory_service: Annotated[MemoryService, Depends(memory_service_from_request)],
) -> UserMemoryOut:
    """Create a new user memory."""
    record = await memory_service.add_memory(
        user_id=current_user.id,
        memory_type=body.memory_type,
        content=body.content,
        confidence=body.confidence,
        source=body.source,
    )
    return UserMemoryOut.model_validate(record)


@router.post("/facts", response_model=MemoryFactOut)
async def create_fact(
    body: FactCreateRequest,
    current_user: Annotated[UserDTO, Depends(get_current_user)],
    memory_service: Annotated[MemoryService, Depends(memory_service_from_request)],
) -> MemoryFactOut:
    """Create a new memory fact."""
    record = await memory_service.add_fact(
        user_id=current_user.id,
        fact_type=body.fact_type,
        content=body.content,
        embedding=body.embedding,
    )
    return MemoryFactOut.model_validate(record)


@router.delete("/facts/{fact_id}", status_code=204)
async def delete_fact(
    fact_id: UUID,
    current_user: Annotated[UserDTO, Depends(get_current_user)],
    memory_service: Annotated[MemoryService, Depends(memory_service_from_request)],
) -> None:
    """Delete a memory fact."""
    await memory_service.delete_fact(fact_id, current_user.id)
