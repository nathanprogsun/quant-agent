"""Chat + SSE routes."""

from __future__ import annotations

from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.common.runs.manager import MultitaskStrategy
from app.common.runs.schemas import DisconnectMode
from app.core.chat.agent.lead_agent import make_lead_agent
from app.core.chat.service.thread_service import ThreadService
from app.db.models.user import User
from app.web.api.chat.services import sse_consumer, start_run
from app.web.api.deps import get_current_user
from app.web.lifespan_service import thread_service_from_lifespan

router = APIRouter(prefix="/api/v1/threads", tags=["chat"])

MAX_MESSAGES = 50
MAX_MESSAGE_LENGTH = 32768  # 32KB


# ── Request models ───────────────────────────────────────────


class MessageInput(BaseModel):
    """Accept both backend format (role) and LangChain SDK format (type)."""

    model_config = ConfigDict(populate_by_name=True)

    role: Literal["user", "assistant", "system"] = Field(
        default="user",
        validation_alias="role",
    )
    type: Literal["human", "ai", "system", "tool"] = Field(
        default="human",
        validation_alias="type",
    )
    content: str = Field(..., max_length=MAX_MESSAGE_LENGTH)

    @field_validator("role", "type", mode="before")
    @classmethod
    def _normalize_role_type(cls, v: Any, info: Any) -> Any:
        """Normalize role/type: accept both formats, prefer the non-null one."""
        if v is None:
            return v
        # If the field name matches the incoming key, use it directly
        # Otherwise let the other field handle it
        return v


class RunCreateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    input: dict[str, Any] = Field(
        default_factory=lambda: {"messages": []},
        description="包含 messages 数组的输入",
    )
    config: dict[str, Any] = Field(default_factory=dict)
    context: dict[str, Any] = Field(default_factory=dict)
    stream_mode: list[str] = Field(
        default_factory=lambda: ["values"],
        validation_alias="streamMode",
    )
    on_disconnect: DisconnectMode = Field(
        default=DisconnectMode.CANCEL,
        validation_alias="onDisconnect",
    )
    multitask_strategy: MultitaskStrategy = Field(
        default=MultitaskStrategy.REJECT,
        validation_alias="multitaskStrategy",
    )

    @field_validator("input")
    @classmethod
    def validate_input_messages(cls, v: dict[str, Any]) -> dict[str, Any]:
        messages = v.get("messages", [])
        if len(messages) > MAX_MESSAGES:
            raise ValueError(f"messages 数组长度不能超过 {MAX_MESSAGES}")
        return v


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
