"""Chat + SSE routes."""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.core.chat.agent.lead_agent import make_lead_agent
from app.core.chat.service.thread_service import ThreadService
from app.db.models.user import User
from app.web.api.chat.services import sse_consumer, start_run
from app.web.api.deps import get_current_user
from app.web.lifespan_service import thread_service_from_lifespan

router = APIRouter(prefix="/api/v1/chat", tags=["chat"])


# ── Request models ───────────────────────────────────────────


class RunCreateRequest(BaseModel):
    input: dict[str, Any] = {"messages": []}
    config: dict[str, Any] = {}
    context: dict[str, Any] = {}
    stream_mode: list[str] = ["values"]
    on_disconnect: str = "cancel"
    multitask_strategy: str = "reject"


# ── Routes ───────────────────────────────────────────────────


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
