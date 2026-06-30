"""MCP (Model Context Protocol) integration for quant-agent.

Ports the deer-flow ``deerflow.mcp`` subsystem onto the ``langchain-mcp-adapters``
client. Three responsibilities:

- :mod:`app.mcp.client`     Build server params + the full multi-server dict.
- :mod:`app.mcp.cache`      Lazy-initialize and cache the resolved tool list;
                            load it once at FastAPI startup via ``initialize_mcp_tools``.
- :mod:`app.mcp.session_pool` Persistent, owner-task-based session pool so
                            stdio MCP servers keep their state across calls.
- :mod:`app.mcp.oauth`      OAuth 2.0 token acquisition for HTTP/SSE servers.
- :mod:`app.mcp.tools`      High-level ``get_mcp_tools()`` loader that wires
                            sessions + OAuth + custom interceptors.

The legacy ``app.core.chat.tools.mcp.client.MCPClient`` (an httpx stub) is
preserved as ``_legacy_http_stub.py`` for backward compatibility but is no
longer used by the agent; see its module docstring.
"""

from app.mcp.cache import (
    get_cached_mcp_tools,
    initialize_mcp_tools,
    reset_mcp_tools_cache,
)
from app.mcp.client import build_server_params, build_servers_config
from app.mcp.tools import get_mcp_tools

__all__ = [
    "build_server_params",
    "build_servers_config",
    "get_cached_mcp_tools",
    "get_mcp_tools",
    "initialize_mcp_tools",
    "reset_mcp_tools_cache",
]
