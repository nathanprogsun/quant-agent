"""Share API schemas."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class ShareCreateRequest(BaseModel):
    thread_id: UUID
    title: str | None = None
    code: str = ""
    messages: list[dict[str, Any]] = Field(default_factory=list)
    metrics: dict[str, Any] | None = None


class ShareCreateResponse(BaseModel):
    share_id: str
    url: str


class ShareSnapshotResponse(BaseModel):
    share_id: str
    title: str | None = None
    code: str = ""
    messages: list[dict[str, Any]] = Field(default_factory=list)
    metrics: dict[str, Any] | None = None
