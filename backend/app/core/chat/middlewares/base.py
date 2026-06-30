"""Agent middleware base class."""

from __future__ import annotations

from abc import ABC
from collections.abc import Awaitable, Callable
from typing import Any


class AgentMiddleware(ABC):
    """Agent middleware with four legacy hooks plus two wrap_* interceptors.

    Legacy hooks (before_/after_model/tool) remain unchanged for backward
    compatibility with the existing 8 middlewares. New code should prefer
    wrap_model_call / wrap_tool_call which give full control over the
    call site and can short-circuit, transform, or retry.
    """

    # ----- Legacy hooks (existing) -----

    async def before_model(
        self, state: dict[str, Any], config: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Before LLM call. Return modified state or None."""
        return None

    async def after_model(
        self, state: dict[str, Any], config: dict[str, Any]
    ) -> dict[str, Any] | None:
        """After LLM call. Return modified state or None."""
        return None

    async def before_tool(
        self, tool_name: str, tool_input: dict[str, Any], config: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Before tool call. Return modified tool_input or None."""
        return None

    async def after_tool(
        self, tool_name: str, tool_input: dict[str, Any], result: Any, config: dict[str, Any]
    ) -> Any | None:
        """After tool call. Return modified result or None."""
        return None

    # ----- Wrap interceptors (new) -----

    async def awrap_model_call(
        self,
        request: Any,
        handler: Callable[[Any], Awaitable[Any]],
    ) -> Any:
        """Async wrap around the model call. Default delegates to handler.

        Subclasses override to inspect/modify `request`, call `handler`,
        and transform the result. Returning without calling handler
        short-circuits the model call.
        """
        return await handler(request)

    def wrap_model_call(
        self,
        request: Any,
        handler: Callable[[Any], Any],
    ) -> Any:
        """Sync wrap around the model call. Default delegates to handler."""
        return handler(request)

    async def awrap_tool_call(
        self,
        request: Any,
        handler: Callable[[Any], Awaitable[Any]],
    ) -> Any:
        """Async wrap around a tool call. Default delegates to handler.

        Required by P2.3 DeferredToolFilter (deer-flow overrides
        `awrap_tool_call` to gate/redirect deferred tool calls). Returning
        without calling handler short-circuits the tool call.
        """
        return await handler(request)

    def wrap_tool_call(
        self,
        request: Any,
        handler: Callable[[Any], Any],
    ) -> Any:
        """Sync wrap around a tool call. Default delegates to handler."""
        return handler(request)
