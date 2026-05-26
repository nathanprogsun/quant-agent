"""Agent middleware base class."""

from __future__ import annotations

from abc import ABC
from typing import Any


class AgentMiddleware(ABC):
    """Agent middleware with four hook points.

    Subclasses only override the hooks they need.
    All hooks return None (no-op) by default.
    """

    async def before_model(
        self, state: dict[str, Any], config: dict
    ) -> dict[str, Any] | None:
        """Before LLM call. Return modified state or None."""
        return None

    async def after_model(
        self, state: dict[str, Any], config: dict
    ) -> dict[str, Any] | None:
        """After LLM call. Return modified state or None."""
        return None

    async def before_tool(
        self, tool_name: str, tool_input: dict, config: dict
    ) -> dict | None:
        """Before tool call. Return modified tool_input or None."""
        return None

    async def after_tool(
        self, tool_name: str, tool_input: dict, result: Any, config: dict
    ) -> Any | None:
        """After tool call. Return modified result or None."""
        return None
