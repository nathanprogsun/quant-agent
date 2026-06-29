"""LangGraph SDK compatibility for thread/run schemas."""

from __future__ import annotations

import asyncio
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from fastapi import Request
from langgraph.checkpoint.base import BaseCheckpointSaver

from app.common.runs.manager import RunManager
from app.common.runs.schemas import DisconnectMode
from app.common.stream_bridge.memory import MemoryStreamBridge
from app.core.chat.service.thread_service import ThreadService
from app.web.api.thread.schema import RunCreateRequest, ThreadResponse
from app.web.api.thread.services import start_run


def test_thread_response_serializes_id_and_thread_id() -> None:
    thread_id = uuid4()
    user_id = uuid4()
    response = ThreadResponse(
        id=thread_id,
        user_id=user_id,
        title="demo",
        model_name="gpt-4o-mini",
    )

    data = response.model_dump(mode="json")

    assert data["id"] == str(thread_id)
    assert data["thread_id"] == str(thread_id)


def test_run_create_request_accepts_stream_mode_camel_case() -> None:
    request = RunCreateRequest.model_validate({"streamMode": "messages"})

    assert request.stream_mode == ["messages"]


@pytest.mark.asyncio
async def test_start_run_forwards_stream_modes(monkeypatch: pytest.MonkeyPatch) -> None:

    captured: dict[str, list[str]] = {}
    started = asyncio.Event()

    async def fake_run_agent(*_args: object, **kwargs: object) -> None:
        captured["stream_modes"] = kwargs["stream_modes"]  # type: ignore[assignment]
        started.set()

    monkeypatch.setattr("app.web.api.thread.services.run_agent", fake_run_agent)

    bridge = MemoryStreamBridge(queue_maxsize=10)
    run_manager = RunManager()
    thread_service = MagicMock(spec=ThreadService)
    thread_service.create = AsyncMock()

    request = MagicMock(spec=Request)
    request.state.current_user_id = uuid4()

    body = RunCreateRequest(
        input={"messages": []},
        stream_mode=["messages", "values"],
        on_disconnect=DisconnectMode.CANCEL,
    )

    await start_run(
        bridge=bridge,
        run_manager=run_manager,
        thread_service=thread_service,
        checkpointer=cast(BaseCheckpointSaver[Any], None),
        body=body,
        thread_id=UUID(str(uuid4())),
        request=request,
        agent_factory=lambda config: MagicMock(),
    )

    await asyncio.wait_for(started.wait(), timeout=1.0)

    assert captured["stream_modes"] == ["messages", "values"]
