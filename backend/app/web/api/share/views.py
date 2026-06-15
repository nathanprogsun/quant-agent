"""Share API routes."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends

from app.core.backtest.errors import BacktestError
from app.core.share.registry import get_share_registry
from app.db.models.user import User
from app.web.api.deps import get_current_user
from app.web.api.share.schemas import (
    ShareCreateRequest,
    ShareCreateResponse,
    ShareSnapshotResponse,
)

router = APIRouter(prefix="/api/v1/share", tags=["share"])


@router.post("", response_model=ShareCreateResponse)
async def create_share(
    body: ShareCreateRequest,
    current_user: Annotated[User, Depends(get_current_user)],
) -> ShareCreateResponse:
    registry = get_share_registry()
    snapshot: dict[str, Any] = {
        "thread_id": str(body.thread_id),
        "title": body.title,
        "code": body.code,
        "messages": body.messages,
        "metrics": body.metrics,
    }
    share_id = registry.create(current_user.id, snapshot)
    return ShareCreateResponse(
        share_id=share_id,
        url=f"/workspace/share/{share_id}",
    )


@router.get("/{share_id}", response_model=ShareSnapshotResponse)
async def get_share(
    share_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
) -> ShareSnapshotResponse:
    registry = get_share_registry()
    snapshot = registry.get(share_id)
    if snapshot is None:
        raise BacktestError(
            message="分享不存在",
            code="share_not_found",
            status_code=404,
        )
    return ShareSnapshotResponse(
        share_id=share_id,
        title=snapshot.get("title"),
        code=snapshot.get("code", ""),
        messages=snapshot.get("messages", []),
        metrics=snapshot.get("metrics"),
    )
