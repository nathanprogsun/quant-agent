"""Memory middleware - injects user memory context before model calls."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from langchain_core.messages import HumanMessage

from app.core.chat.middlewares.base import AgentMiddleware
from app.db.dao.memory_repository import MemoryRepository

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


logger = logging.getLogger(__name__)

# Session factory reference - set during app initialization
_session_factory: async_sessionmaker[AsyncSession] | None = None


def set_memory_middleware_session_factory(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Set the session factory for memory middleware.

    Called during app initialization to inject the factory.
    """
    global _session_factory
    _session_factory = session_factory


class MemoryMiddleware(AgentMiddleware):
    """Injects user memory context before model call.

    Retrieves the user's memory context from the database and
    injects it into the state for the LLM to consume.
    """

    async def before_model(
        self, state: dict[str, Any], config: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Inject memory context into messages.

        Retrieves user_id from config and fetches memory context,
        then injects a system message with the memory context.
        """
        if _session_factory is None:
            logger.warning("Memory middleware: no session factory configured")
            return None

        configurable = config.get("configurable", {})
        user_id = configurable.get("user_id")

        if not user_id:
            logger.debug("Memory middleware: no user_id in config")
            return None

        try:
            # Extract plain data inside session to avoid DetachedInstanceError.
            async with _session_factory() as session:
                repo = MemoryRepository(session=session)
                memories = await repo.find_memories_by_user(user_id)
                facts = await repo.find_facts_by_user(user_id)

                memory_data: list[tuple[str, float, str | None]] = [
                    (m.content, m.confidence, m.source) for m in memories
                ]
                fact_data: list[str] = [f.content for f in facts]

            if not memory_data and not fact_data:
                return None

            # Build context string (no ORM access beyond this point)
            sections: list[str] = []
            if memory_data:
                sections.append("[User Memories]")
                for content, confidence, source in memory_data:
                    confidence_str = (
                        f" (confidence: {confidence:.0%})"
                        if confidence < 1.0
                        else ""
                    )
                    source_str = f" [source: {source}]" if source else ""
                    sections.append(f"- {content}{confidence_str}{source_str}")

            if fact_data:
                sections.append("[User Facts]")
                for content in fact_data:
                    sections.append(f"- {content}")

            context_string = "\n".join(sections)

            # Inject after system message if present
            messages = list(state.get("messages", []))
            if not messages:
                return None

            # Check if memory context already injected
            if any(
                "[User Memories]" in str(m.content) or "[User Facts]" in str(m.content)
                for m in messages
            ):
                return None

            memory_context = (
                f"\n\n[User Memory Context]\n{context_string}\n"
                "Use this context to personalize responses based on the user's known preferences and facts."
            )

            # Inject after first system message if present, else at start
            if (
                len(messages) > 0
                and hasattr(messages[0], "type")
                and messages[0].type == "system"
            ):
                # Insert after system message
                messages.insert(1, HumanMessage(content=memory_context))
            else:
                messages.insert(0, HumanMessage(content=memory_context))

            return {"messages": messages}

        except Exception as e:
            logger.error(f"Memory middleware error: {e}")
            return None
