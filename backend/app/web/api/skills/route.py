"""Skills API routes."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.core.chat.skills.registry import (
    SkillDefinition,
    SkillParameter,
    get_skill_registry,
)
from app.db.models.user import User
from app.web.api.deps import get_current_user

router = APIRouter(prefix="/api/skills", tags=["skills"])


def skill_registry_from_request(request: Request) -> Any:
    """Get SkillRegistry from app context."""
    return get_skill_registry()


# ── Request models ───────────────────────────────────────────


class SkillCreateRequest(BaseModel):
    """Request to register a new skill."""

    name: str = Field(..., min_length=1, max_length=128, description="Unique skill name")
    description: str = Field(..., min_length=1, max_length=1024, description="Skill description")
    version: str = Field(default="1.0.0", description="Semantic version")
    parameters: list[SkillParameter] = Field(default_factory=list, description="Input parameters")
    prompt_template: str = Field(..., min_length=1, description="Prompt template for LLM")
    tools: list[str] = Field(default_factory=list, description="Required tool names")
    max_iterations: int = Field(default=5, ge=1, le=50, description="Max agentic iterations")


class SkillResponse(BaseModel):
    """Response containing skill definition."""

    name: str
    description: str
    version: str
    parameters: list[SkillParameter]
    prompt_template: str
    tools: list[str]
    max_iterations: int


class SkillListResponse(BaseModel):
    """Response containing list of skills."""

    skills: list[SkillResponse]
    total: int


# ── Routes ───────────────────────────────────────────────────


@router.get("", response_model=SkillListResponse)
async def list_skills(
    current_user: Annotated[User, Depends(get_current_user)],
    registry: Annotated[Any, Depends(skill_registry_from_request)],
) -> SkillListResponse:
    """List all registered skills.

    Returns all available skills that can be executed by the agent.
    """
    skills = registry.list_all()
    return SkillListResponse(
        skills=[
            SkillResponse(
                name=s.name,
                description=s.description,
                version=s.version,
                parameters=s.parameters,
                prompt_template=s.prompt_template,
                tools=s.tools,
                max_iterations=s.max_iterations,
            )
            for s in skills
        ],
        total=len(skills),
    )


@router.get("/{skill_name}", response_model=SkillResponse)
async def get_skill(
    skill_name: str,
    current_user: Annotated[User, Depends(get_current_user)],
    registry: Annotated[Any, Depends(skill_registry_from_request)],
) -> SkillResponse:
    """Get skill details by name.

    Args:
        skill_name: Name of skill to retrieve.

    Returns:
        Skill definition.

    Raises:
        404: If skill not found.
    """
    skill = registry.get(skill_name)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill not found: {skill_name}")
    return SkillResponse(
        name=skill.name,
        description=skill.description,
        version=skill.version,
        parameters=skill.parameters,
        prompt_template=skill.prompt_template,
        tools=skill.tools,
        max_iterations=skill.max_iterations,
    )


@router.post("", response_model=SkillResponse, status_code=201)
async def create_skill(
    body: SkillCreateRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    registry: Annotated[Any, Depends(skill_registry_from_request)],
) -> SkillResponse:
    """Register a new skill.

    Creates a new skill definition that can be executed by the agent.

    Args:
        body: Skill definition to register.

    Returns:
        Created skill definition.
    """
    skill = SkillDefinition(
        name=body.name,
        description=body.description,
        version=body.version,
        parameters=body.parameters,
        prompt_template=body.prompt_template,
        tools=body.tools,
        max_iterations=body.max_iterations,
    )
    registry.register(skill)
    return SkillResponse(
        name=skill.name,
        description=skill.description,
        version=skill.version,
        parameters=skill.parameters,
        prompt_template=skill.prompt_template,
        tools=skill.tools,
        max_iterations=skill.max_iterations,
    )


@router.delete("/{skill_name}", status_code=204)
async def delete_skill(
    skill_name: str,
    current_user: Annotated[User, Depends(get_current_user)],
    registry: Annotated[Any, Depends(skill_registry_from_request)],
) -> None:
    """Unregister a skill.

    Removes a skill from the registry.

    Args:
        skill_name: Name of skill to unregister.

    Raises:
        404: If skill not found.
    """
    deleted = registry.unregister(skill_name)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Skill not found: {skill_name}")
