"""Memory database models."""

from datetime import datetime
from uuid import UUID

from app.db.models.core.base import Column, JsonColumn, TableModel


class UserMemory(TableModel):
    """User memory table model.

    Stores user memories with type classification, confidence scores,
    and source attribution.
    """

    table_name = "user_memories"
    schema_name = ""
    ordered_primary_keys = ("id",)

    id: Column[UUID]
    user_id: Column[UUID]
    memory_type: Column[str]  # e.g., "preference", "fact", "context", "goal"
    content: Column[str]
    confidence: Column[float] = 1.0  # 0.0 to 1.0
    source: Column[str | None] = None  # e.g., "chat", "profile", "explicit"
    created_at: Column[datetime]
    updated_at: Column[str | None] = None


class MemoryFact(TableModel):
    """Memory fact table model.

    Stores structured facts extracted from user interactions.
    Includes embedding vector for similarity search.
    """

    table_name = "memory_facts"
    schema_name = ""
    ordered_primary_keys = ("id",)

    id: Column[UUID]
    user_id: Column[UUID]
    fact_type: Column[str]  # e.g., "preference", "knowledge", "plan", "relationship"
    content: Column[str]
    embedding: JsonColumn[list[float] | None] = None  # Vector embedding for similarity
    created_at: Column[datetime]
    updated_at: Column[str | None] = None
