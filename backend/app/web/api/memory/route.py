"""Memory API routes."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.core.chat.memory.service import MemoryService
from app.db.models.memory import MemoryFact, UserMemory
from app.db.models.user import User
from app.web.api.deps import get_current_user

router = APIRouter(prefix="/api/memory", tags=["memory"])


def memory_service_from_request(request: Request) -> MemoryService:
    """Get MemoryService from app context."""
    app_context = request.app.state.app_context
    if not app_context or not app_context.lifespan_service:
        raise HTTPException(status_code=500, detail="Memory service not initialized")
    # MemoryService is created on-demand via factory
    from app.core.chat.memory.service import MemoryService
    from app.db.dao.memory_repository import MemoryRepository

    repo = MemoryRepository(engine=app_context.main_db)
    return MemoryService(memory_repository=repo)


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


# ── Response models ───────────────────────────────────────────


class MemoryContextResponse(BaseModel):
    """Response containing user memory context."""

    memories: list[UserMemory]
    facts: list[MemoryFact]
    context_string: str = Field(description="Formatted context string for prompts")


# ── Routes ───────────────────────────────────────────────────


@router.get("", response_model=MemoryContextResponse)
async def get_memory_context(
    current_user: Annotated[User, Depends(get_current_user)],
    memory_service: Annotated[MemoryService, Depends(memory_service_from_request)],
) -> MemoryContextResponse:
    """Get aggregated memory context for the current user.

    Returns all user memories and facts formatted for prompt injection.
    """
    context = await memory_service.get_user_memory(current_user.id)
    return MemoryContextResponse(
        memories=context.memories,
        facts=context.facts,
        context_string=context.to_prompt_string(),
    )


@router.post("/memories", response_model=UserMemory)
async def create_memory(
    body: MemoryCreateRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    memory_service: Annotated[MemoryService, Depends(memory_service_from_request)],
) -> UserMemory:
    """Create a new user memory."""
    return await memory_service.add_memory(
        user_id=current_user.id,
        memory_type=body.memory_type,
        content=body.content,
        confidence=body.confidence,
        source=body.source,
    )


@router.post("/facts", response_model=MemoryFact)
async def create_fact(
    body: FactCreateRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    memory_service: Annotated[MemoryService, Depends(memory_service_from_request)],
) -> MemoryFact:
    """Create a new memory fact."""
    return await memory_service.add_fact(
        user_id=current_user.id,
        fact_type=body.fact_type,
        content=body.content,
        embedding=body.embedding,
    )


@router.delete("/facts/{fact_id}")
async def delete_fact(
    fact_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    memory_service: Annotated[MemoryService, Depends(memory_service_from_request)],
) -> dict[str, bool]:
    """Delete a memory fact."""
    deleted = await memory_service.delete_fact(fact_id, current_user.id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Fact not found")
    return {"deleted": True}
