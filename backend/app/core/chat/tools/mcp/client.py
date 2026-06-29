"""MCP client for connecting to MCP servers."""

from __future__ import annotations

from typing import Any, cast

import httpx


class MCPClient:
    """Client for connecting to MCP (Model Context Protocol) servers.

    MCP servers provide tools that can be used by the agent.
    This client handles connection, tool discovery, and tool execution.

    Example:
        client = MCPClient("http://localhost:8080")
        await client.connect_server()
        tools = await client.get_tools()
        result = await client.execute_tool("search", {"query": "test"})
        await client.disconnect_server()
    """

    def __init__(self, server_url: str, timeout: int = 60):
        """Initialize MCP client.

        Args:
            server_url: URL of the MCP server.
            timeout: Request timeout in seconds.
        """
        self.server_url = server_url.rstrip("/")
        self.timeout = timeout
        self._connected = False
        self._client: httpx.AsyncClient | None = None

    async def connect_server(self) -> None:
        """Connect to the MCP server.

        Establishes the connection and verifies the server is available.
        """
        if self._connected and self._client:
            return

        self._client = httpx.AsyncClient(
            base_url=self.server_url,
            timeout=self.timeout,
        )

        # Verify connection by calling the server info endpoint
        try:
            response = await self._client.get("/")
            response.raise_for_status()
            self._connected = True
        except Exception as e:
            self._client = None
            self._connected = False
            raise ConnectionError(f"Failed to connect to MCP server: {e}")

    async def disconnect_server(self) -> None:
        """Disconnect from the MCP server.

        Cleans up the connection and resources.
        """
        if self._client:
            await self._client.aclose()
            self._client = None
        self._connected = False

    async def get_tools(self) -> list[dict[str, Any]]:
        """Get available tools from the MCP server.

        Returns:
            List of tool definitions from the server.
        """
        if not self._connected or not self._client:
            raise RuntimeError("Not connected to MCP server. Call connect_server first.")

        try:
            response = await self._client.get("/tools")
            response.raise_for_status()
            data = response.json()
            return cast(list[dict[str, Any]], data.get("tools", []))
        except Exception as e:
            raise RuntimeError(f"Failed to get tools from MCP server: {e}")

    async def execute_tool(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
    ) -> Any:
        """Execute a tool on the MCP server.

        Args:
            tool_name: Name of the tool to execute.
            tool_input: Input arguments for the tool.

        Returns:
            Result from the tool execution.
        """
        if not self._connected or not self._client:
            raise RuntimeError("Not connected to MCP server. Call connect_server first.")

        try:
            response = await self._client.post(
                "/tools/execute",
                json={
                    "name": tool_name,
                    "input": tool_input,
                },
            )
            response.raise_for_status()
            data = response.json()
            return data.get("result")
        except httpx.HTTPStatusError as e:
            raise RuntimeError(f"Tool execution failed with status {e.response.status_code}: {e}")
        except Exception as e:
            raise RuntimeError(f"Tool execution failed: {e}")

    @property
    def is_connected(self) -> bool:
        """Check if client is connected to server.

        Returns:
            True if connected, False otherwise.
        """
        return self._connected
