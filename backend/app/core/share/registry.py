"""In-memory share snapshot registry."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4


class ShareRegistry:
    def __init__(self) -> None:
        self._snapshots: dict[str, dict[str, Any]] = {}
        self._owners: dict[str, UUID] = {}

    def create(self, user_id: UUID, snapshot: dict[str, Any]) -> str:
        share_id = str(uuid4())
        self._snapshots[share_id] = snapshot
        self._owners[share_id] = user_id
        return share_id

    def get(self, share_id: str) -> dict[str, Any] | None:
        return self._snapshots.get(share_id)

    def is_owner(self, share_id: str, user_id: UUID) -> bool:
        owner = self._owners.get(share_id)
        return owner is not None and owner == user_id


_share_registry = ShareRegistry()


def get_share_registry() -> ShareRegistry:
    return _share_registry
