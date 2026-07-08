"""Regression tests: sync I/O paths must not block the asyncio event loop."""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain.agents.middleware import ModelRequest
from langchain_core.messages import HumanMessage
from llama_index.core import QueryBundle

from app.util.asyncio_util.adapter import run_in_pool


@pytest.mark.asyncio
async def test_run_in_pool_allows_concurrent_progress() -> None:
    """While a blocking op runs in the pool, other coroutines stay scheduled."""
    progress: list[str] = []

    async def heartbeat() -> None:
        for _ in range(3):
            await asyncio.sleep(0.05)
            progress.append("tick")

    def slow_sync() -> str:
        time.sleep(0.15)
        return "done"

    result, _ = await asyncio.gather(
        run_in_pool(slow_sync),
        heartbeat(),
    )
    assert result == "done"
    assert len(progress) >= 2


@pytest.mark.asyncio
async def test_embedding_model_offloads_to_pool() -> None:
    from app.core.jq_kb.embedding_model import EmbeddingModel  # noqa: PLC0415

    with patch(
        "app.core.jq_kb.embedding_model.run_in_pool",
        new_callable=AsyncMock,
    ) as mock_pool:
        mock_pool.return_value = [0.1, 0.2]
        model = EmbeddingModel()
        out = await model._aget_query_embedding("hello")
        mock_pool.assert_awaited_once()
        assert out == [0.1, 0.2]


@pytest.mark.asyncio
async def test_rerank_nodes_async_uses_thread_pool() -> None:
    from app.core.jq_kb.async_helpers import rerank_nodes_async  # noqa: PLC0415

    reranker = MagicMock()
    reranker.postprocess_nodes.return_value = ["reranked"]
    bundle = QueryBundle(query_str="q")
    nodes = ["n1"]

    with patch(
        "app.core.jq_kb.async_helpers.run_in_pool",
        new_callable=AsyncMock,
    ) as mock_pool:
        mock_pool.return_value = ["reranked"]
        out = await rerank_nodes_async(reranker, nodes, bundle)
        mock_pool.assert_awaited_once_with(
            reranker.postprocess_nodes,
            None,
            nodes,
            query_bundle=bundle,
        )
        assert out == ["reranked"]


@pytest.mark.asyncio
async def test_skill_activation_middleware_offloads_disk_io() -> None:
    from app.core.chat.middlewares.skill_activation_middleware import (  # noqa: PLC0415
        SkillActivationMiddleware,
    )

    storage = MagicMock()
    mw = SkillActivationMiddleware(storage=storage)
    request = ModelRequest(model=MagicMock(), messages=[HumanMessage(content="hello", id="u1")])

    async def handler(req: ModelRequest) -> str:
        return "ok"

    with patch(
        "app.core.chat.middlewares.skill_activation_middleware.asyncio.to_thread",
        new_callable=AsyncMock,
    ) as mock_thread:
        mock_thread.return_value = None
        result = await mw.awrap_model_call(request, handler)
        mock_thread.assert_awaited_once_with(
            mw._prepare_model_request, request, hook="awrap_model_call"
        )
        assert result == "ok"


@pytest.mark.asyncio
async def test_read_file_tool_arun_offloads_to_pool(tmp_path) -> None:
    from app.core.chat.tools.builtin.read_file_tool import ReadFileTool  # noqa: PLC0415

    container = tmp_path / "skill"
    container.mkdir()
    (container / "SKILL.md").write_text("body", encoding="utf-8")
    tool = ReadFileTool(containers=[tmp_path])

    with patch(
        "app.core.chat.tools.builtin.read_file_tool.run_in_pool",
        new_callable=AsyncMock,
    ) as mock_pool:
        mock_pool.return_value = "body"
        out = await tool._arun(container_path=str(container), file_path="SKILL.md")
        mock_pool.assert_awaited_once_with(tool._read, None, str(container), "SKILL.md")
        assert out == "body"


@pytest.mark.asyncio
async def test_make_lead_agent_async_prefetches_mcp_without_sync_wait(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core.chat.agent import lead_agent as la_mod  # noqa: PLC0415

    sentinel_graph = MagicMock(name="graph")
    mcp_tools = [MagicMock(name="mcp_tool")]

    async def fake_mcp_async() -> list:
        return mcp_tools

    monkeypatch.setattr("app.mcp.cache.get_cached_mcp_tools_async", fake_mcp_async)

    with patch.object(la_mod, "make_lead_agent", return_value=sentinel_graph) as mock_build:
        graph = await la_mod.make_lead_agent_async({"configurable": {}})
        mock_build.assert_called_once()
        assert mock_build.call_args.kwargs["mcp_tools"] is mcp_tools
        assert graph is sentinel_graph


@pytest.mark.asyncio
async def test_concurrent_retrieve_shortcuts_do_not_serially_block() -> None:
    """Two metadata lookups offloaded via run_in_pool should overlap in time."""
    from app.core.jq_kb.retrievers import JqApiRetriever  # noqa: PLC0415

    store = MagicMock()
    delays: list[float] = []

    def slow_lookup(name: str):
        start = time.monotonic()
        time.sleep(0.08)
        delays.append(time.monotonic() - start)
        return {"id": "1", "document": "d", "metadata": {"function_name": name}}

    store.get_by_function_name.side_effect = slow_lookup
    retriever = JqApiRetriever(store=store)

    started = time.monotonic()
    await asyncio.gather(
        retriever.retrieve_by_function_name("a"),
        retriever.retrieve_by_function_name("b"),
    )
    elapsed = time.monotonic() - started

    # Sequential would be ~0.16s; parallel thread pool should finish closer to ~0.08s.
    assert elapsed < 0.14
    assert len(delays) == 2
