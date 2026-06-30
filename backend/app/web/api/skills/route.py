"""Skills API routes."""

from __future__ import annotations

from typing import Annotated, cast

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from app.common.exception import ResourceNotFoundError, ServiceError
from app.core.chat.skills.registry import (
    SkillDefinition,
    SkillParameter,
    SkillRegistry,
)
from app.db.models.user import User
from app.skills.exceptions import SkillNotFoundError
from app.web.api.deps import get_current_user
from app.web.api.skills.service import (
    SkillMetadata,
    SkillsService,
    make_skills_service_from_settings,
)

router = APIRouter(prefix="/api/skills", tags=["skills"])


def skill_registry_from_request(request: Request) -> SkillRegistry:
    """Get SkillRegistry from app context."""
    app_context = getattr(request.app.state, "app_context", None)
    if app_context is None or app_context.skill_registry is None:
        raise ServiceError("Skill registry not initialized")
    return cast(SkillRegistry, app_context.skill_registry)


def skills_service_from_request(request: Request) -> SkillsService:
    """Build a SkillsService, preferring an override on app state (tests)."""
    override = getattr(request.app.state, "skills_service", None)
    if override is not None:
        return cast(SkillsService, override)
    return make_skills_service_from_settings()


# ── Request / response models ───────────────────────────────────


class SkillCreateRequest(BaseModel):
    """Request to register a new skill."""

    name: str = Field(..., min_length=1, max_length=128, description="Unique skill name")
    description: str = Field(
        ..., min_length=1, max_length=1024, description="Human-readable description"
    )
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


class SkillToggleRequest(BaseModel):
    """Request body for the skill enable/disable toggle."""

    enabled: bool = Field(description="Whether the skill should be enabled")


class SkillDisclosureResponse(BaseModel):
    """Metadata-only skill view (progressive disclosure)."""

    name: str
    description: str
    category: str
    container_path: str
    enabled: bool


class SkillDisclosureListResponse(BaseModel):
    """List of metadata-only skills."""

    skills: list[SkillDisclosureResponse]
    total: int


# ── Progressive-disclosure routes (P1.5) ───────────────────────
# Registered BEFORE the /{skill_name} routes so /disclosure is not shadowed.


@router.get("/disclosure", response_model=SkillDisclosureListResponse)
async def list_skill_disclosure(
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[SkillsService, Depends(skills_service_from_request)],
) -> SkillDisclosureListResponse:
    """List disk-discovered skills with their runtime enabled state."""
    skills: list[SkillMetadata] = service.list_skills()
    return SkillDisclosureListResponse(
        skills=[
            SkillDisclosureResponse(
                name=s.name,
                description=s.description,
                category=s.category,
                container_path=s.container_path,
                enabled=s.enabled,
            )
            for s in skills
        ],
        total=len(skills),
    )


@router.put("/{skill_name}", response_model=SkillDisclosureResponse)
async def toggle_skill(
    skill_name: str,
    body: SkillToggleRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[SkillsService, Depends(skills_service_from_request)],
) -> SkillDisclosureResponse:
    """Toggle a skill's enabled state and invalidate the prompt cache.

    Writes the new state to ``extensions_config.json`` and drops the LRU
    skills-prompt cache so the next agent turn reflects the change.
    """
    try:
        meta = service.set_enabled(skill_name, enabled=body.enabled)
    except SkillNotFoundError as e:
        raise ResourceNotFoundError(str(e)) from e
    return SkillDisclosureResponse(
        name=meta.name,
        description=meta.description,
        category=meta.category,
        container_path=meta.container_path,
        enabled=meta.enabled,
    )


# ── Legacy registry routes ─────────────────────────────────────


@router.get("", response_model=SkillListResponse)
async def list_skills(
    current_user: Annotated[User, Depends(get_current_user)],
    registry: Annotated[SkillRegistry, Depends(skill_registry_from_request)],
) -> SkillListResponse:
    """List all registered skills."""
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
    registry: Annotated[SkillRegistry, Depends(skill_registry_from_request)],
) -> SkillResponse:
    """Get skill details by name.

    Raises:
        404: If skill not found.
    """
    skill = registry.get(skill_name)
    if not skill:
        raise ResourceNotFoundError(f"Skill not found: {skill_name}")
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
    registry: Annotated[SkillRegistry, Depends(skill_registry_from_request)],
) -> SkillResponse:
    """Register a new skill."""
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
    registry: Annotated[SkillRegistry, Depends(skill_registry_from_request)],
) -> None:
    """Unregister a skill.

    Raises:
        404: If skill not found.
    """
    deleted = registry.unregister(skill_name)
    if not deleted:
        raise ResourceNotFoundError(f"Skill not found: {skill_name}")
