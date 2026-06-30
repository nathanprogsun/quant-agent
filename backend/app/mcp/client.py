"""Build per-server params + the full MultiServerMCPClient config.

Port of ``deerflow.mcp.client`` (lines 11-69). Stateless helpers — no
side effects on import. The ``tools.py`` loader calls ``build_servers_config``
to derive the dict that MultiServerMCPClient expects.

Supported transports (mapped to langchain-mcp-adapters keys):

============== ===========================
type / transport params emitted to MultiServerMCPClient
============== ===========================
stdio            ``command``, ``args``, ``env``
sse / http       ``url``, ``headers``
============== ===========================
"""

from __future__ import annotations

import logging
from typing import Any

from app.config.extensions_config import ExtensionsConfig, McpServerConfig

logger = logging.getLogger(__name__)


def build_server_params(
    server_name: str,
    config: McpServerConfig,
    *,
    resolve_secrets: bool = True,
) -> dict[str, Any]:
    """Build server parameters for MultiServerMCPClient.

    The returned dict is one entry of the per-server config consumed by
    ``langchain_mcp_adapters.client.MultiServerMCPClient``. Validation is
    fail-fast (raises ``ValueError`` when a required field is missing);
    callers (e.g. ``build_servers_config``) may choose to skip instead.

    When ``resolve_secrets=True`` (the default), ``$TOKEN``-style strings
    inside ``args``/``env``/``headers`` are interpolated from the process
    environment at call time. Pass ``resolve_secrets=False`` only when
    you need to inspect raw templates (tests).
    """
    transport_type = config.type or "stdio"
    params: dict[str, Any] = {"transport": transport_type}

    def _resolved(value: object) -> object:
        if not resolve_secrets:
            return value
        return ExtensionsConfig.resolve_env_variables(value)

    def _as_str_list(value: object) -> list[str]:
        """Coerce a possibly-resolved list of strings back to ``list[str]``."""
        if isinstance(value, list):
            return [str(item) for item in value]
        return []

    def _as_str_dict(value: object) -> dict[str, str]:
        """Coerce a possibly-resolved dict back to ``dict[str, str]``."""
        if isinstance(value, dict):
            return {str(k): str(v) for k, v in value.items()}
        return {}

    if transport_type == "stdio":
        if not config.command:
            raise ValueError(
                f"MCP server '{server_name}' with stdio transport requires 'command' field"
            )
        params["command"] = config.command
        params["args"] = _as_str_list(_resolved(config.args))
        if config.env:
            params["env"] = _as_str_dict(_resolved(config.env))
    elif transport_type in ("sse", "http"):
        if not config.url:
            raise ValueError(
                f"MCP server '{server_name}' with {transport_type} transport requires 'url' field"
            )
        params["url"] = config.url
        if config.headers:
            params["headers"] = _as_str_dict(_resolved(config.headers))
    else:
        raise ValueError(
            f"MCP server '{server_name}' has unsupported transport type: {transport_type}"
        )

    return params


def build_servers_config(
    extensions_config: ExtensionsConfig,
    *,
    resolve_secrets: bool = True,
) -> dict[str, dict[str, Any]]:
    """Build the multi-server config consumed by MultiServerMCPClient.

    Iterates ``extensions_config.get_enabled_mcp_servers()`` and emits one
    entry per server. Servers that fail to validate are logged at ERROR and
    skipped — a single bad config must not block healthy servers from
    contributing tools.
    """
    enabled_servers = extensions_config.get_enabled_mcp_servers()

    if not enabled_servers:
        logger.info("No enabled MCP servers found")
        return {}

    servers_config: dict[str, dict[str, Any]] = {}
    for server_name, server_config in enabled_servers.items():
        try:
            servers_config[server_name] = build_server_params(
                server_name, server_config, resolve_secrets=resolve_secrets
            )
            logger.info(f"Configured MCP server: {server_name}")
        except Exception as exc:
            logger.error(f"Failed to configure MCP server '{server_name}': {exc}")

    return servers_config
