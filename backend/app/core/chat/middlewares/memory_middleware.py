"""Memory middleware - injects user memory context before model calls."""

from __future__ import annotations

import logging
from typing import Any

from app.core.chat.middlewares.base import AgentMiddleware
from app.db.dao.memory_repository import MemoryRepository
from app.db.dbengine.core import DatabaseEngine

logger = logging.getLogger(__name__)

# Database engine reference - set during app initialization
_db_engine: DatabaseEngine | None = None


def set_memory_middleware_engine(engine: DatabaseEngine) -> None:
    """Set the database engine for memory middleware.

    Called during app initialization to inject the engine.
    """
    global _db_engine
    _db_engine = engine


class MemoryMiddleware(AgentMiddleware):
    """Injects user memory context before model call.

    Retrieves the user's memory context from the database and
    injects it into the state for the LLM to consume.
    """

    async def before_model(self, state: dict[str, Any], config: dict[str, Any]) -> dict[str, Any] | None:
        """Inject memory context into messages.

        Retrieves user_id from config and fetches memory context,
        then injects a system message with the memory context.
        """
        if _db_engine is None:
            logger.warning("Memory middleware: no database engine configured")
            return None

        configurable = config.get("configurable", {})
        user_id = configurable.get("user_id")

        if not user_id:
            logger.debug("Memory middleware: no user_id in config")
            return None

        try:
            repo = MemoryRepository(engine=_db_engine)
            memories = await repo.find_memories_by_user(user_id)
            facts = await repo.find_facts_by_user(user_id)

            if not memories and not facts:
                return None

            # Build context string
            sections: list[str] = []
            if memories:
                sections.append("[User Memories]")
                for mem in memories:
                    confidence_str = f" (confidence: {mem.confidence:.0%})" if mem.confidence < 1.0 else ""
                    source_str = f" [source: {mem.source}]" if mem.source else ""
                    sections.append(f"- {mem.content}{confidence_str}{source_str}")

            if facts:
                sections.append("[User Facts]")
                for fact in facts:
                    sections.append(f"- {fact.content}")

            context_string = "\n".join(sections)

            # Inject after system message if present
            messages = list(state.get("messages", []))
            if not messages:
                return None

            # Check if memory context already injected
            if any("[User Memories]" in str(m.content) or "[User Facts]" in str(m.content) for m in messages):
                return None

            memory_context = (
                f"\n\n[User Memory Context]\n{context_string}\n"
                "Use this context to personalize responses based on the user's known preferences and facts."
            )

            from langchain_core.messages import HumanMessage

            # Inject after first system message if present, else at start
            if len(messages) > 0 and hasattr(messages[0], "type") and messages[0].type == "system":
                # Insert after system message
                messages.insert(1, HumanMessage(content=memory_context))
            else:
                messages.insert(0, HumanMessage(content=memory_context))

            return {"messages": messages}

        except Exception as e:
            logger.error(f"Memory middleware error: {e}")
            return None
