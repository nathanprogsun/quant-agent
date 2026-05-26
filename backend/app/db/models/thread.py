from datetime import datetime
from uuid import UUID

from app.db.models.core.base import Column, TableModel


class Thread(TableModel):
    table_name = "threads"
    schema_name = ""
    ordered_primary_keys = ("id",)

    id: Column[UUID]
    user_id: Column[UUID]
    title: Column[str | None] = None
    model_name: Column[str | None] = None
    created_at: Column[datetime]
    updated_at: Column[str | None] = None
    deleted_at: Column[datetime | None] = None
