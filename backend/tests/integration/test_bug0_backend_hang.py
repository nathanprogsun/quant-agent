"""Bug-0 regression test: backend hang after long stream with MCP tool calls.

This test reproduces the scenario where the backend hangs after a long stream
chat request with multiple MCP tool calls. The bug manifests as all subsequent
requests timing out.

Feedback loop:
1. Mock MCP tools to simulate slow tool calls
2. Run a stream that triggers multiple tool calls
3. After stream completes, verify health endpoint still responds
4. If health check times out, the bug is reproduced (RED)
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.tools import StructuredTool

from tests.integration.client import APITestClient


def _create_mock_mcp_tool(name: str, delay: float = 0.5) -> StructuredTool:
    """Create a mock MCP tool that simulates a slow tool call."""

    async def slow_coroutine(*args: Any, **kwargs: Any) -> str:
        await asyncio.sleep(delay)
        return f"Result from {name}"

    return StructuredTool(
        name=name,
        description=f"Mock tool {name}",
        args_schema={"type": "object", "properties": {}},
        coroutine=slow_coroutine,
        metadata={"quant_agent_mcp": True},
    )


@pytest.mark.asyncio
async def test_backend_does_not_hang_after_long_stream_with_mcp_tools(
    authed_api_client: APITestClient,
) -> None:
    """Backend remains responsive after a long stream with multiple MCP tool calls.

    This test reproduces Bug-0: after a long stream chat with 4+ MCP tool calls,
    the backend hangs and stops responding to all requests.

    The test:
    1. Mocks MCP tools with slow responses
    2. Creates a thread and runs a stream that triggers tool calls
    3. After stream completes, checks if health endpoint responds
    4. If health check times out (5s), the bug is reproduced
    """
    # Create mock MCP tools that simulate slow tool calls
    mock_tools = [
        _create_mock_mcp_tool("mcp_tool_1", delay=0.3),
        _create_mock_mcp_tool("mcp_tool_2", delay=0.3),
        _create_mock_mcp_tool("mcp_tool_3", delay=0.3),
        _create_mock_mcp_tool("mcp_tool_4", delay=0.3),
    ]

    # Patch get_mcp_tools to return our mock tools
    with patch("app.mcp.tools.get_mcp_tools", new_callable=AsyncMock) as mock_get_tools:
        mock_get_tools.return_value = mock_tools

        # Also patch initialize_mcp_tools for the lifespan
        with patch("app.mcp.initialize_mcp_tools", new_callable=AsyncMock) as mock_init:
            mock_init.return_value = mock_tools

            # Create a thread
            created = await authed_api_client.post(
                "/api/v1/threads",
                json={"title": "Bug-0 test thread"},
            )
            thread_id = created["id"]

            # Run a stream that should trigger tool calls
            # We use a simple input - the agent should use the mock tools
            status, _headers, _events = await authed_api_client.post_sse(
                f"/api/v1/threads/{thread_id}/runs/stream",
                json={
                    "input": {
                        "messages": [
                            {"role": "user", "content": "Use the MCP tools to help me"},
                        ],
                    },
                },
            )

            assert status == 200, f"Stream request failed with status {status}"

            # Wait a bit for any cleanup tasks to complete
            await asyncio.sleep(1.0)

            # Now check if the backend is still responsive
            # This is the critical check - if the backend hung, this will timeout
            try:
                health_status, _ = await asyncio.wait_for(
                    authed_api_client.get_raw("/health"),
                    timeout=5.0,
                )
                assert health_status == 200, f"Health check failed with status {health_status}"
            except TimeoutError:
                pytest.fail(
                    "Bug-0 reproduced: backend hung after long stream with MCP tools. "
                    "Health check timed out after 5 seconds."
                )


@pytest.mark.asyncio
async def test_backend_responds_after_multiple_concurrent_streams(
    authed_api_client: APITestClient,
) -> None:
    """Backend remains responsive after multiple concurrent streams.

    This test checks if concurrent streams cause resource exhaustion or deadlocks.
    """
    # Create multiple threads and run concurrent streams
    threads = []
    for i in range(3):
        created = await authed_api_client.post(
            "/api/v1/threads",
            json={"title": f"Concurrent test {i}"},
        )
        threads.append(created["id"])

    # Run concurrent streams
    async def run_stream(thread_id: str) -> tuple[int, list]:
        status, _, events = await authed_api_client.post_sse(
            f"/api/v1/threads/{thread_id}/runs/stream",
            json={
                "input": {
                    "messages": [
                        {"role": "user", "content": f"Hello from thread {thread_id}"},
                    ],
                },
            },
        )
        return status, events

    results = await asyncio.gather(*[run_stream(tid) for tid in threads])

    # All streams should succeed
    for i, (status, events) in enumerate(results):
        assert status == 200, f"Stream {i} failed with status {status}"

    # Check if backend is still responsive
    try:
        health_status, _ = await asyncio.wait_for(
            authed_api_client.get_raw("/health"),
            timeout=5.0,
        )
        assert health_status == 200
    except TimeoutError:
        pytest.fail("Backend hung after concurrent streams")


@pytest.mark.asyncio
async def test_stream_cleanup_does_not_block_event_loop(
    authed_api_client: APITestClient,
) -> None:
    """Stream cleanup tasks do not block the event loop.

    This test checks if the cleanup tasks (bridge.cleanup, run_manager.cleanup)
    block the event loop and prevent other requests from being processed.
    """
    # Create a thread
    created = await authed_api_client.post(
        "/api/v1/threads",
        json={"title": "Cleanup test thread"},
    )
    thread_id = created["id"]

    # Run a stream
    status, _, _ = await authed_api_client.post_sse(
        f"/api/v1/threads/{thread_id}/runs/stream",
        json={
            "input": {
                "messages": [
                    {"role": "user", "content": "Hello"},
                ],
            },
        },
    )
    assert status == 200

    # Immediately after stream completes, check if backend responds
    # If cleanup tasks block the event loop, this will be slow or timeout
    try:
        health_status, _ = await asyncio.wait_for(
            authed_api_client.get_raw("/health"),
            timeout=2.0,
        )
        assert health_status == 200
    except TimeoutError:
        pytest.fail("Backend hung during stream cleanup - event loop blocked")
