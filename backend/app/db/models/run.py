from datetime import datetime
from typing import Any
from uuid import UUID

from app.db.models.core.base import Column, JsonColumn, TableModel


class Run(TableModel):
    table_name = "runs"
    schema_name = ""
    ordered_primary_keys = ("id",)

    id: Column[UUID]
    thread_id: Column[UUID]
    user_id: Column[UUID]
    status: Column[str]
    model_name: Column[str | None] = None
    assistant_id: Column[str | None] = None
    error_message: Column[str | None] = None
    token_usage: JsonColumn[dict[str, Any] | None] = None
    created_at: Column[datetime]
    finished_at: Column[datetime | None] = None
