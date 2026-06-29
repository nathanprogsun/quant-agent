from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Body, Depends, Request
from fastapi.responses import StreamingResponse

from app.core.chat.agent.lead_agent import make_lead_agent
from app.core.chat.service.history_service import (
    HistoryService,
    history_service_from_request,
)
from app.core.chat.service.state_service import StateService, state_service_from_request
from app.core.chat.service.thread_service import RunService, ThreadService
from app.db.models.user import User
from app.web.api.deps import get_current_user
from app.web.api.thread.schema import (
    CancelResponse,
    CreateThreadRequest,
    HistoryRequest,
    RunCreateRequest,
    RunListResponse,
    RunResponse,
    StateUpdateRequest,
    ThreadListResponse,
    ThreadResponse,
    UpdateTitleRequest,
)
from app.web.api.thread.services import sse_consumer, start_run
from app.web.lifespan_service import (
    run_service_from_request,
    thread_service_from_request,
)

router = APIRouter(prefix="/api/v1/threads", tags=["threads"])


@router.get("", response_model=ThreadListResponse)
async def list_threads(
    current_user: Annotated[User, Depends(get_current_user)],
    thread_service: Annotated[ThreadService, Depends(thread_service_from_request)],
    limit: int = 50,
    offset: int = 0,
) -> ThreadListResponse:
    """List threads for the current user."""
    threads = await thread_service.list_by_user_id(
        current_user.id, limit=limit, offset=offset
    )
    return ThreadListResponse(
        threads=[
            ThreadResponse(
                id=t.id,
                user_id=t.user_id,
                title=t.title,
                model_name=t.model_name,
                created_at=t.created_at,
                updated_at=t.updated_at,
            )
            for t in threads
        ]
    )


@router.post("", response_model=ThreadResponse, status_code=201)
async def create_thread(
    current_user: Annotated[User, Depends(get_current_user)],
    thread_service: Annotated[ThreadService, Depends(thread_service_from_request)],
    body: Annotated[CreateThreadRequest | None, Body()] = None,
) -> ThreadResponse:
    """Create a new thread.

    All fields are optional. If ``thread_id`` (or its ``threadId`` alias) is
    omitted, the service generates a UUID. The request body may also be empty
    or missing entirely.
    """

    payload = body or CreateThreadRequest()
    thread = await thread_service.create(
        thread_id=payload.resolved_thread_id or uuid4(),
        user_id=current_user.id,
        title=payload.title,
        model_name=payload.model_name,
    )
    return ThreadResponse(
        id=thread.id,
        user_id=thread.user_id,
        title=thread.title,
        model_name=thread.model_name,
        created_at=thread.created_at,
        updated_at=thread.updated_at,
    )


@router.get("/{thread_id}", response_model=ThreadResponse)
async def get_thread(
    thread_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    thread_service: Annotated[ThreadService, Depends(thread_service_from_request)],
) -> ThreadResponse:
    """Get thread by ID."""
    thread = await thread_service.get(thread_id, current_user.id)
    return ThreadResponse(
        id=thread.id,
        user_id=thread.user_id,
        title=thread.title,
        model_name=thread.model_name,
        created_at=thread.created_at,
        updated_at=thread.updated_at,
    )


@router.patch("/{thread_id}", response_model=ThreadResponse)
async def update_thread(
    thread_id: UUID,
    body: UpdateTitleRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    thread_service: Annotated[ThreadService, Depends(thread_service_from_request)],
) -> ThreadResponse:
    """Update thread title."""
    thread = await thread_service.update_title_or_raise(
        thread_id, current_user.id, body.title
    )
    return ThreadResponse(
        id=thread.id,
        user_id=thread.user_id,
        title=thread.title,
        model_name=thread.model_name,
        created_at=thread.created_at,
        updated_at=thread.updated_at,
    )


@router.delete("/{thread_id}", status_code=204)
async def delete_thread(
    thread_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    thread_service: Annotated[ThreadService, Depends(thread_service_from_request)],
) -> None:
    """Soft delete a thread."""
    await thread_service.delete_or_raise(thread_id, current_user.id)


@router.get("/{thread_id}/runs", response_model=RunListResponse)
async def list_runs(
    thread_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    run_service: Annotated[RunService, Depends(run_service_from_request)],
) -> RunListResponse:
    """List all runs for a thread (owner-only).

    Non-owners see the same response as no-runs; we don't disclose other users' runs.
    """
    records = await run_service.list_for_user(thread_id, current_user.id)
    return RunListResponse(runs=[RunResponse.from_run_record(r) for r in records])


@router.get("/{thread_id}/runs/{run_id}", response_model=RunResponse)
async def get_run(
    thread_id: UUID,
    run_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    run_service: Annotated[RunService, Depends(run_service_from_request)],
) -> RunResponse:
    """Get a specific run by ID."""
    record = await run_service.get_for_user(run_id, thread_id, current_user.id)
    return RunResponse.from_run_record(record)


@router.post("/{thread_id}/runs/stream")
async def stream_run(
    thread_id: UUID,
    body: RunCreateRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    thread_service: Annotated[ThreadService, Depends(thread_service_from_request)],
    run_service: Annotated[RunService, Depends(run_service_from_request)],
    request: Request,
) -> StreamingResponse:
    """Create a run and stream events via SSE."""
    app_context = request.app.state.app_context

    await thread_service.assert_stream_access(thread_id, current_user.id)

    record = await start_run(
        bridge=app_context.stream_bridge,
        run_manager=run_service.manager,
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
            run_manager=run_service.manager,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "Content-Location": f"/api/v1/threads/{thread_id}/runs/{record.run_id}",
        },
    )


@router.post("/{thread_id}/runs/{run_id}/cancel", response_model=CancelResponse)
async def cancel_run(
    thread_id: UUID,
    run_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    run_service: Annotated[RunService, Depends(run_service_from_request)],
) -> CancelResponse:
    """Cancel a running run (owner-only)."""
    await run_service.cancel_for_user(run_id, thread_id, current_user.id)
    return CancelResponse(status="cancelled", run_id=run_id)


@router.get("/{thread_id}/history")
async def get_thread_history(
    thread_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    history_service: Annotated[HistoryService, Depends(history_service_from_request)],
) -> dict[str, Any]:
    """Legacy GET history — returns latest checkpoint messages."""
    return await history_service.get_latest_messages(thread_id, current_user.id)


@router.post("/{thread_id}/history")
async def post_thread_history(
    thread_id: UUID,
    body: HistoryRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    history_service: Annotated[HistoryService, Depends(history_service_from_request)],
) -> list[dict[str, Any]]:
    """Return checkpoint history in LangGraph SDK ThreadState shape."""
    return await history_service.list_history(thread_id, current_user.id, body)


@router.get("/{thread_id}/state")
async def get_thread_state(
    thread_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    history_service: Annotated[HistoryService, Depends(history_service_from_request)],
) -> dict[str, Any]:
    """Return latest thread state in LangGraph SDK shape."""
    return await history_service.get_state(thread_id, current_user.id)


@router.post("/{thread_id}/state")
async def post_thread_state(
    thread_id: UUID,
    body: StateUpdateRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    state_service: Annotated[StateService, Depends(state_service_from_request)],
) -> dict[str, Any]:
    """Update thread state values and return the new ThreadState snapshot."""
    return await state_service.apply_update(thread_id, current_user.id, body)
