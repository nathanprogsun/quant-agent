"""LEGACY — httpx-based MCP client stub.

.. deprecated::
    Replaced by :mod:`app.mcp` (langchain-mcp-adapters based) in P2.2.
    This stub is preserved only so external imports of
    ``app.core.chat.tools.mcp.client.MCPClient`` keep working until the
    next minor release. New code MUST use ``app.mcp`` helpers
    (``build_server_params``, ``get_mcp_tools``, etc.).
"""

from __future__ import annotations

from typing import Any, cast

import httpx


class MCPClient:
    """Legacy httpx-based client.

    Kept for backward compatibility with code that imported
    ``app.core.chat.tools.mcp.client.MCPClient`` before P2.2. Do not use
    for new functionality; the production entry point is ``app.mcp.get_mcp_tools``.
    """

    def __init__(self, server_url: str, timeout: int = 60):
        self.server_url = server_url.rstrip("/")
        self.timeout = timeout
        self._connected = False
        self._client: httpx.AsyncClient | None = None

    async def connect_server(self) -> None:
        if self._connected and self._client:
            return

        self._client = httpx.AsyncClient(base_url=self.server_url, timeout=self.timeout)
        try:
            response = await self._client.get("/")
            response.raise_for_status()
            self._connected = True
        except Exception as e:
            self._client = None
            self._connected = False
            raise ConnectionError(f"Failed to connect to MCP server: {e}") from e

    async def disconnect_server(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
        self._connected = False

    async def get_tools(self) -> list[dict[str, Any]]:
        if not self._connected or not self._client:
            raise RuntimeError("Not connected to MCP server. Call connect_server first.")

        try:
            response = await self._client.get("/tools")
            response.raise_for_status()
            data = response.json()
            return cast(list[dict[str, Any]], data.get("tools", []))
        except Exception as e:
            raise RuntimeError(f"Failed to get tools from MCP server: {e}") from e

    async def execute_tool(self, tool_name: str, tool_input: dict[str, Any]) -> Any:
        if not self._connected or not self._client:
            raise RuntimeError("Not connected to MCP server. Call connect_server first.")

        try:
            response = await self._client.post(
                "/tools/execute",
                json={"name": tool_name, "input": tool_input},
            )
            response.raise_for_status()
            data = response.json()
            return data.get("result")
        except httpx.HTTPStatusError as e:
            raise RuntimeError(
                f"Tool execution failed with status {e.response.status_code}: {e}"
            ) from e
        except Exception as e:
            raise RuntimeError(f"Tool execution failed: {e}") from e

    @property
    def is_connected(self) -> bool:
        return self._connected


__all__ = ["MCPClient"]
