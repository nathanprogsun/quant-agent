"""Verify sqlite checkpointer stays open for the app lifetime."""

from __future__ import annotations

import pytest
from langgraph.checkpoint.base import Checkpoint, RunnableConfig

from app.app_context.app_context import AppContext


@pytest.mark.integration
async def test_checkpointer_aput_and_aget(test_app_context: AppContext) -> None:
    checkpointer = test_app_context.checkpointer
    assert checkpointer is not None

    config: RunnableConfig = {
        "configurable": {
            "thread_id": "integration-test-thread",
            "checkpoint_ns": "",
        },
    }
    checkpoint: Checkpoint = {
        "v": 1,
        "id": "test-checkpoint-1",
        "ts": "2026-06-14T00:00:00Z",
        "channel_values": {"messages": [{"role": "user", "content": "hello"}]},
        "channel_versions": {},
        "versions_seen": {},
        "updated_channels": None,
    }

    await checkpointer.aput(config, checkpoint, {}, {})
    loaded = await checkpointer.aget(config)

    assert loaded is not None
    assert loaded["channel_values"]["messages"] == checkpoint["channel_values"]["messages"]
