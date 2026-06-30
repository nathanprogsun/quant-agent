"""MCP shim — kept for backward compatibility with imports of
``app.core.chat.tools.mcp.client.MCPClient``.

The active MCP implementation lives at :mod:`app.mcp` (langchain-mcp-adapters
based, ported in P2.2). Anything still importing the legacy httpx stub
will get a ``DeprecationWarning`` from ``_legacy_http_stub``.
"""

import warnings

from app.core.chat.tools.mcp._legacy_http_stub import MCPClient

warnings.warn(
    "app.core.chat.tools.mcp is deprecated; use app.mcp instead.",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = ["MCPClient"]
