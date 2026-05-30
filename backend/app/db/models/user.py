"""User database model.

Note: `user` is a reserved keyword in PostgreSQL. The `table_name = "user"`
requires quoting in raw SQL queries (e.g., `FROM "user"`).

Unlike SysTableModel, User does not use the framework-managed `sys_updated_at`
field, so it inherits from TableModel directly.
"""

from datetime import datetime
from uuid import UUID

from app.db.models.core.base import Column, TableModel


class User(TableModel):
    """User table model."""

    table_name = "users"
    schema_name = ""  # Empty for SQLite compatibility
    ordered_primary_keys = ("id",)

    id: Column[UUID]
    email: Column[str]
    username: Column[str | None] = None
    full_name: Column[str | None] = None
    hashed_password: Column[str]
    is_active: Column[bool] = True
    is_superuser: Column[bool] = False
    token_version: Column[int] = 0  # 密码修改后递增，使旧 token 失效
    created_at: Column[datetime]
    updated_at: Column[str | None] = None
