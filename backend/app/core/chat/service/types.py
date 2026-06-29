"""Typed DTOs for chat service."""

from typing import TYPE_CHECKING, Any
from uuid import UUID

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from langchain_core.messages.base import BaseMessage


class GraphMessage(BaseModel):
    """A message in the graph input."""

    role: str = "user"
    content: str
    type: str | None = None
    name: str | None = None

    model_config = {"extra": "allow"}


class GraphInput(BaseModel):
    """Typed graph input for agent invocation."""

    messages: list[GraphMessage] = Field(default_factory=list)
    thread_id: UUID | None = None
    user_id: UUID | None = None
    # Allow other LangGraph state fields
    model_config = {"extra": "allow"}

    @classmethod
    def from_langchain_messages(
        cls,
        messages: list["BaseMessage"],
        **extra: Any,
    ) -> "GraphInput":
        """Build GraphInput from a list of LangChain BaseMessage objects."""
        converted: list[GraphMessage] = []
        for msg in messages:
            converted.append(
                GraphMessage(
                    role=getattr(msg, "type", "user"),
                    content=getattr(msg, "content", "") or "",
                    name=getattr(msg, "name", None),
                )
            )
        return cls(messages=converted, **extra)


__all__ = ["GraphInput", "GraphMessage"]
