"""Service for thread state writes (LangGraph checkpointer integration)."""

from __future__ import annotations

from typing import Annotated, Any, cast
from uuid import UUID

from fastapi import Depends
from langgraph.checkpoint.base import BaseCheckpointSaver, Checkpoint, CheckpointMetadata
from sqlalchemy.ext.asyncio import AsyncSession

from app.app_context.app_context import AppContext
from app.db.dao.thread_repository import ThreadRepository
from app.web.api.thread.checkpoint_state import (
    checkpoint_tuple_to_thread_state,
    empty_thread_state,
    new_checkpoint,
    thread_config,
)
from app.web.api.thread.schema import StateUpdateRequest
from app.web.lifespan_service import get_app_context, session_from_app_context


class StateService:
    """Encapsulates LangGraph checkpoint writes for thread state updates."""

    def __init__(
        self,
        session: AsyncSession,
        checkpointer: BaseCheckpointSaver[Any] | None,
    ) -> None:
        self._session = session
        self._checkpointer = checkpointer

    async def _assert_thread_access(self, thread_id: UUID, user_id: UUID) -> None:
        """Verify thread exists and is owned by user."""
        await ThreadRepository(self._session).find_by_id_and_user_or_fail(
            thread_id, user_id
        )

    async def apply_update(
        self,
        thread_id: UUID,
        user_id: UUID,
        body: StateUpdateRequest,
    ) -> dict[str, Any]:
        """Apply a state update and return the resulting ThreadState snapshot.

        Returns the empty state when no body.values are provided, or when
        the checkpointer is unavailable. Otherwise merges values into the
        latest checkpoint and writes a new one.
        """
        if not body.values:
            if self._checkpointer is None:
                return empty_thread_state(thread_id)
            config = thread_config(thread_id)
            checkpoint_tuple = await self._checkpointer.aget_tuple(config)
            if checkpoint_tuple is None:
                return empty_thread_state(thread_id)
            return checkpoint_tuple_to_thread_state(checkpoint_tuple)

        await self._assert_thread_access(thread_id, user_id)

        if self._checkpointer is None:
            return empty_thread_state(thread_id)

        config = thread_config(thread_id)
        if body.checkpoint is not None:
            configurable: dict[str, Any] = {
                **(config.get("configurable") or {}),
                **body.checkpoint,
            }
            config = {"configurable": configurable, "metadata": config.get("metadata") or {}}
        if body.checkpoint_id is not None:
            configurable = dict(config.get("configurable") or {})
            configurable["checkpoint_id"] = body.checkpoint_id
            config = {"configurable": configurable, "metadata": config.get("metadata") or {}}

        checkpoint_tuple = await self._checkpointer.aget_tuple(config)
        if checkpoint_tuple is None:
            checkpoint: Checkpoint = new_checkpoint(dict(body.values))
            metadata: CheckpointMetadata = {}
            write_config = config
        else:
            channel_values = dict(
                checkpoint_tuple.checkpoint.get("channel_values") or {}
            )
            channel_values.update(body.values)
            checkpoint = cast(Checkpoint, dict(checkpoint_tuple.checkpoint))
            checkpoint["channel_values"] = channel_values
            metadata = checkpoint_tuple.metadata
            write_config = checkpoint_tuple.config

        next_config = await self._checkpointer.aput(
            write_config,
            checkpoint,
            metadata,
            {},
        )
        next_tuple = await self._checkpointer.aget_tuple(next_config)
        if next_tuple is None:
            return empty_thread_state(thread_id)
        return checkpoint_tuple_to_thread_state(next_tuple)


def state_service_from_request(
    session: Annotated[AsyncSession, Depends(session_from_app_context)],
    app_context: Annotated[AppContext, Depends(get_app_context)],
) -> StateService:
    """Build a StateService bound to the request session and app checkpointer."""
    return StateService(session=session, checkpointer=app_context.checkpointer)
