"""Agent middleware base class — delegates to langchain ABC.

Inherits from ``langchain.agents.middleware.AgentMiddleware`` so all
hook methods have ``Runtime``-based signatures. Provides default no-op
``wrap_*`` implementations (langchain's defaults raise
NotImplementedError) because ``lead_agent.py`` invokes
``awrap_model_call`` on ALL middlewares in the chain, not just those
that override it.

Concrete middlewares override the hooks they need. ``Runtime`` is
re-exported here for convenience.
"""

from __future__ import annotations

from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langgraph.runtime import Runtime


class AgentMiddleware(AgentMiddleware):
    """quant-agent's AgentMiddleware — no-op wrap delegates by default.

    All hooks mirror langchain's AgentMiddleware signature, with the
    exception of ``wrap_*`` / ``awrap_*`` which use bare ``Any`` for
    the request/handler types (langchain expects typed
    ``ModelRequest``/``ToolCallRequest``). This is compatible at runtime
    since quant-agent's ``_run_awrap_model_call`` passes
    ``ModelCallRequest`` (not ``ModelRequest``). Concrete middlewares
    override the hooks they need.
    """

    # ----- Wrap interceptors with no-op defaults -----
    # langchain's AgentMiddleware raises NotImplementedError for these.
    # quant-agent invokes awrap_model_call on the full middleware chain,
    # so every middleware must have a usable default.

    def wrap_model_call(self, request: Any, handler: Any) -> Any:
        return handler(request)

    async def awrap_model_call(self, request: Any, handler: Any) -> Any:
        return await handler(request)

    def wrap_tool_call(self, request: Any, handler: Any) -> Any:
        return handler(request)

    async def awrap_tool_call(self, request: Any, handler: Any) -> Any:
        return await handler(request)


__all__ = ["AgentMiddleware", "Runtime"]
