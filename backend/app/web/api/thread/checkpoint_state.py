"""Serialize LangGraph checkpoints into LangGraph SDK ThreadState shape."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from langchain_core.messages import BaseMessage, messages_to_dict
from langgraph.checkpoint.base import Checkpoint, CheckpointTuple, RunnableConfig


def config_to_checkpoint(config: RunnableConfig) -> dict[str, Any]:
    """Map RunnableConfig to SDK Checkpoint object."""
    configurable = config.get("configurable") or {}
    checkpoint: dict[str, Any] = {
        "thread_id": configurable.get("thread_id"),
        "checkpoint_ns": configurable.get("checkpoint_ns", ""),
        "checkpoint_id": configurable.get("checkpoint_id"),
    }
    checkpoint_map = configurable.get("checkpoint_map")
    if checkpoint_map is not None:
        checkpoint["checkpoint_map"] = checkpoint_map
    return checkpoint


def serialize_state_values(values: dict[str, Any]) -> dict[str, Any]:
    """Serialize channel values for JSON responses."""
    if not values:
        return {}

    serialized = dict(values)
    messages = serialized.get("messages")
    if (
        isinstance(messages, list)
        and messages
        and isinstance(messages[0], BaseMessage)
    ):
        serialized["messages"] = messages_to_dict(messages)
    return serialized


def checkpoint_tuple_to_thread_state(
    checkpoint_tuple: CheckpointTuple,
) -> dict[str, Any]:
    """Convert a CheckpointTuple into SDK-compatible ThreadState."""
    checkpoint = checkpoint_tuple.checkpoint or {}
    channel_values = checkpoint.get("channel_values") or {}

    parent_checkpoint = None
    if checkpoint_tuple.parent_config is not None:
        parent_checkpoint = config_to_checkpoint(checkpoint_tuple.parent_config)

    return {
        "values": serialize_state_values(channel_values),
        "next": [],
        "checkpoint": config_to_checkpoint(checkpoint_tuple.config),
        "metadata": checkpoint_tuple.metadata or {},
        "created_at": checkpoint.get("ts"),
        "parent_checkpoint": parent_checkpoint,
        "tasks": [],
    }


def empty_thread_state(thread_id: UUID) -> dict[str, Any]:
    """Default ThreadState when no checkpoint exists yet."""
    thread_id_str = str(thread_id)
    return {
        "values": {},
        "next": [],
        "checkpoint": {
            "thread_id": thread_id_str,
            "checkpoint_ns": "",
            "checkpoint_id": None,
        },
        "metadata": {},
        "created_at": None,
        "parent_checkpoint": None,
        "tasks": [],
    }


def thread_config(thread_id: UUID) -> RunnableConfig:
    """Build RunnableConfig for a thread's root checkpoint namespace."""
    return RunnableConfig(
        configurable={
            "thread_id": str(thread_id),
            "checkpoint_ns": "",
        }
    )


def new_checkpoint(channel_values: dict[str, Any]) -> Checkpoint:
    """Create a minimal checkpoint payload for first-time state writes."""
    return {
        "v": 1,
        "id": str(uuid4()),
        "ts": datetime.now(UTC).isoformat(),
        "channel_values": channel_values,
        "channel_versions": {},
        "versions_seen": {},
        "updated_channels": None,
    }
