"""SSE stream contract tests for chat runs."""

from __future__ import annotations

from typing import Any

import pytest

from app.settings import get_settings
from tests.conftest import is_openai_api_key_configured
from tests.integration.client import APITestClient


def _assistant_text_from_events(events: list[tuple[str, Any]]) -> str:
    """Extract assistant message text from values/messages SSE payloads."""
    chunks: list[str] = []

    for event_name, data in events:
        if event_name == "messages" and isinstance(data, list) and len(data) == 2:
            chunk = data[0]
            if isinstance(chunk, dict):
                content = chunk.get("content")
                if isinstance(content, str) and content.strip():
                    chunks.append(content.strip())
            continue

        if event_name not in {"values", "messages"} or not isinstance(data, dict):
            continue

        messages = data.get("messages")
        if not isinstance(messages, list):
            continue

        for message in messages:
            if not isinstance(message, dict):
                continue

            role = message.get("type") or message.get("role")
            if role not in {"ai", "assistant", "AIMessage", "AIMessageChunk"}:
                continue

            content = message.get("content")
            if isinstance(content, str) and content.strip():
                chunks.append(content.strip())
                continue

            data_block = message.get("data")
            if isinstance(data_block, dict):
                nested = data_block.get("content")
                if isinstance(nested, str) and nested.strip():
                    chunks.append(nested.strip())

    if not chunks:
        return ""

    return max(chunks, key=len, default="")


def _message_chunk_events(events: list[tuple[str, Any]]) -> list[list[Any]]:
    """Return SSE payloads shaped as [chunk, metadata] tuples."""
    return [
        data
        for event_name, data in events
        if event_name == "messages" and isinstance(data, list) and len(data) == 2
    ]


@pytest.mark.asyncio
@pytest.mark.skipif(
    not is_openai_api_key_configured(),
    reason="Requires OPENAI_API_KEY in environment or backend/.env",
)
async def test_chat_stream_contract(
    authed_api_client: APITestClient,
    require_working_llm: None,
) -> None:
    """Stream exposes metadata, state chunks, end, Content-Location, and assistant text."""
    settings = get_settings()
    created = await authed_api_client.post(
        "/api/v1/threads",
        json={"model_name": settings.model},
    )
    thread_id = created["id"]

    status, headers, events = await authed_api_client.post_sse(
        f"/api/v1/threads/{thread_id}/runs/stream",
        json={
            "input": {
                "messages": [
                    {"role": "user", "content": "Reply with the single word: hello"},
                ],
            },
            "context": {"model_name": settings.model},
        },
    )

    assert status == 200

    content_location = headers.get("content-location", "")
    assert content_location.startswith(f"/api/v1/threads/{thread_id}/runs/")
    run_id = content_location.rsplit("/", maxsplit=1)[-1]
    assert len(run_id) == 36

    event_names = [name for name, _ in events]
    assert "metadata" in event_names
    assert "end" in event_names
    assert event_names.index("metadata") < event_names.index("end")
    assert any(name in {"values", "messages"} for name in event_names)

    metadata = next(data for name, data in events if name == "metadata")
    assert metadata["thread_id"] == thread_id
    assert metadata["run_id"] == run_id

    error_payloads = [data for name, data in events if name == "error"]
    assert not error_payloads, f"SSE error event: {error_payloads}"

    assistant_text = _assistant_text_from_events(events)
    assert assistant_text.strip(), "expected non-empty assistant content in values/messages events"

    message_events = _message_chunk_events(events)
    assert len(message_events) >= 2, "expected multiple incremental messages events"

    thread = await authed_api_client.get(f"/api/v1/threads/{thread_id}")
    assert thread["title"] == "Reply with the single word: hello"
