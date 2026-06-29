"""Service for thread history operations (LangGraph checkpointer integration)."""

from __future__ import annotations

from typing import Annotated, Any, cast
from uuid import UUID

from fastapi import Depends
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from sqlalchemy.ext.asyncio import AsyncSession

from app.app_context.app_context import AppContext
from app.db.dao.thread_repository import ThreadRepository
from app.web.api.thread.checkpoint_state import (
    checkpoint_tuple_to_thread_state,
    empty_thread_state,
    serialize_state_values,
    thread_config,
)
from app.web.api.thread.schema import HistoryRequest
from app.web.lifespan_service import get_app_context, session_from_app_context


class HistoryService:
    """Encapsulates LangGraph checkpoint history queries.

    History and state are read from the LangGraph checkpointer, not from
    our SQL tables. This service handles empty-checkpointer fallback and
    builds configs from request payloads.
    """

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

    async def get_latest_messages(self, thread_id: UUID, user_id: UUID) -> dict[str, Any]:
        """Return latest checkpoint messages as dict."""
        await self._assert_thread_access(thread_id, user_id)
        if self._checkpointer is None:
            return {"messages": []}
        config = thread_config(thread_id)
        checkpoint = await self._checkpointer.aget(config)
        if checkpoint and checkpoint.get("channel_values", {}).get("messages"):
            values = serialize_state_values(checkpoint["channel_values"])
            return {"messages": values.get("messages", [])}
        return {"messages": []}

    async def list_history(
        self,
        thread_id: UUID,
        user_id: UUID,
        body: HistoryRequest,
    ) -> list[dict[str, Any]]:
        """Return list of thread state snapshots matching SDK ThreadState shape."""
        await self._assert_thread_access(thread_id, user_id)
        if self._checkpointer is None:
            return []

        config = thread_config(thread_id)
        before_config: RunnableConfig | None = None
        if body.before is not None:
            before_config = cast(RunnableConfig, {"configurable": body.before})
        elif body.checkpoint is not None:
            before_config = cast(RunnableConfig, {"configurable": body.checkpoint})

        states: list[dict[str, Any]] = []
        async for checkpoint_tuple in self._checkpointer.alist(
            config,
            before=before_config,
            limit=body.limit,
        ):
            states.append(checkpoint_tuple_to_thread_state(checkpoint_tuple))
        return states

    async def get_state(self, thread_id: UUID, user_id: UUID) -> dict[str, Any]:
        """Return current thread state."""
        await self._assert_thread_access(thread_id, user_id)
        if self._checkpointer is None:
            return empty_thread_state(thread_id)
        config = thread_config(thread_id)
        checkpoint_tuple = await self._checkpointer.aget_tuple(config)
        if checkpoint_tuple is None:
            return empty_thread_state(thread_id)
        return checkpoint_tuple_to_thread_state(checkpoint_tuple)


def history_service_from_request(
    session: Annotated[AsyncSession, Depends(session_from_app_context)],
    app_context: Annotated[AppContext, Depends(get_app_context)],
) -> HistoryService:
    """Build a HistoryService bound to the request session and app checkpointer."""
    if app_context.checkpointer is None:
        return HistoryService(session=session, checkpointer=None)
    return HistoryService(session=session, checkpointer=app_context.checkpointer)
