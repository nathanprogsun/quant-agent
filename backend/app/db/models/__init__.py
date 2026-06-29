"""ORM models — all inherit from Base (DeclarativeBase)."""
from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Single declarative base for the whole data layer."""


# Import order matters: leaf models first so relationships can resolve.
from app.db.models.memory import MemoryFact, UserMemory  # noqa: E402
from app.db.models.run import Run  # noqa: E402
from app.db.models.thread import Thread  # noqa: E402
from app.db.models.user import User  # noqa: E402

__all__ = ["Base", "MemoryFact", "Run", "Thread", "User", "UserMemory"]
