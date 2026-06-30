"""High-level loader: ``get_mcp_tools()`` returns LangChain tools for all
enabled MCP servers in ``extensions_config.json``.

Pipeline:

1. ``build_servers_config`` validates and maps ``extensions_config.json``
   onto the per-server dict that ``MultiServerMCPClient`` expects.
2. Initial OAuth headers (for HTTP/SSE) and ``extensions_config.json``-
   declared custom interceptors (paths of the form
   ``pkg.module:builder_callable``) are collected.
3. ``MultiServerMCPClient.get_tools(server_name=...)`` is called per
   server (independent ``asyncio.gather``) so a single broken server
   does not block healthy ones.
4. Stdio-loaded tools are wrapped through ``_make_session_pool_tool`` so
   consecutive calls within a thread reuse the same session. HTTP / SSE
   tools are returned untouched to avoid cross-task ``TaskGroup``
   cleanup errors (see deer-flow issue #3203).
5. ``tools.metadata["quant_agent_mcp"] = True`` tags every loaded tool —
   consumed by :mod:`app.tools.mcp_metadata` to populate deferred
   discovery.
"""

from __future__ import annotations

import asyncio
import logging
from importlib import import_module
from typing import Any

from langchain_core.tools import BaseTool, StructuredTool

from app.config.extensions_config import ExtensionsConfig
from app.mcp.client import build_servers_config
from app.mcp.oauth import build_oauth_tool_interceptor, get_initial_oauth_headers
from app.mcp.session_pool import get_session_pool
from app.tools.sync_tool_wrapper import make_sync_tool_wrapper

logger = logging.getLogger(__name__)

MCP_METADATA_KEY = "quant_agent_mcp"


def _resolve_variable(variable_path: str) -> Any:
    """Import ``pkg.module`` and return the named attribute.

    Mirrors :func:`deerflow.reflection.resolve_variable` with a minimal
    implementation: ``module:variable_name``. Import errors propagate; the
    caller (``get_mcp_tools``) catches and logs them so a single broken
    interceptor does not block tool discovery.
    """
    try:
        module_path, variable_name = variable_path.rsplit(":", 1)
    except ValueError as exc:
        raise ImportError(
            f"{variable_path} doesn't look like a variable path "
            "(expected 'pkg.module:variable_name')"
        ) from exc

    module = import_module(module_path)
    return getattr(module, variable_name)


def _tag_mcp_tool(tool: BaseTool) -> BaseTool:
    """Mutate ``tool.metadata`` to mark it as MCP-sourced and return it."""
    tool.metadata = {**(tool.metadata or {}), MCP_METADATA_KEY: True}
    return tool


async def _make_session_pool_tool(
    tool: BaseTool,
    server_name: str,
    connection: dict[str, Any],
    tool_interceptors: list[Any] | None = None,
) -> BaseTool:
    """Wrap an MCP tool so it reuses a persistent session from the pool.

    Pool sessions are scoped by ``(server_name, user_id:thread_id)`` —
    thread_id alone is insufficient because two users with colliding
    thread_ids would otherwise share one stateful MCP session.
    """
    original_name = tool.name
    prefix = f"{server_name}_"
    if original_name.startswith(prefix):
        original_name = original_name[len(prefix) :]

    pool = get_session_pool()

    async def call_with_persistent_session(runtime: Any = None, **arguments: Any) -> Any:
        thread_id = _extract_thread_id(runtime)
        user_id = _resolve_user_id(runtime)
        scope_key = f"{user_id}:{thread_id}"
        session = await pool.get_session(server_name, scope_key, dict(connection))

        if tool_interceptors:
            from langchain_mcp_adapters.interceptors import MCPToolCallRequest

            async def base_handler(request: Any) -> Any:
                call_kwargs: dict[str, Any] = {}
                if request.headers:
                    call_kwargs["meta"] = {"headers": dict(request.headers)}
                return await session.call_tool(request.name, request.args, **call_kwargs)

            handler = base_handler
            for interceptor in reversed(tool_interceptors):
                outer = handler

                async def wrapped(req: Any, _i: Any = interceptor, _h: Any = outer) -> Any:
                    return await _i(req, _h)

                handler = wrapped  # type: ignore[assignment]

            request = MCPToolCallRequest(
                name=original_name,
                args=arguments,
                server_name=server_name,
                runtime=runtime,
            )
            return await handler(request)

        return await session.call_tool(original_name, arguments)

    return StructuredTool(
        name=tool.name,
        description=tool.description,
        args_schema=tool.args_schema or {},
        coroutine=call_with_persistent_session,
        response_format="content_and_artifact",
        metadata=tool.metadata,
    )


def _extract_thread_id(runtime: Any) -> str:
    """Best-effort thread_id extraction for ``runtime`` (LangChain ToolRuntime)."""
    if runtime is not None:
        tid = getattr(runtime, "context", None)
        if tid is not None and isinstance(tid, dict):
            t = tid.get("thread_id")
            if t is not None:
                return str(t)
        config = getattr(runtime, "config", None)
        if isinstance(config, dict):
            t = config.get("configurable", {}).get("thread_id")
            if t is not None:
                return str(t)
    return "default"


def _resolve_user_id(runtime: Any) -> str:
    """Best-effort user_id extraction."""
    if runtime is not None:
        ctx = getattr(runtime, "context", None)
        if isinstance(ctx, dict):
            u = ctx.get("user_id")
            if u is not None:
                return str(u)
    return "default"


async def get_mcp_tools() -> list[BaseTool]:
    """Resolve every enabled MCP server's tools, wrapped for session reuse."""
    try:
        from langchain_mcp_adapters.client import MultiServerMCPClient
    except ImportError:
        logger.warning(
            "langchain-mcp-adapters not installed. Install it via "
            "`uv add langchain-mcp-adapters` to enable MCP tools."
        )
        return []

    extensions_config_obj: ExtensionsConfig
    cfg_path = ExtensionsConfig.resolve_config_path()
    if cfg_path is not None and cfg_path.exists():
        extensions_config_obj = ExtensionsConfig.from_file(cfg_path)
    else:
        # No file on disk — start with an empty config. The empty case is
        # the common one in unit tests; production deploys ship a real
        # extensions_config.json.
        extensions_config_obj = ExtensionsConfig()

    servers_config = build_servers_config(extensions_config_obj)

    if not servers_config:
        logger.info("No enabled MCP servers configured")
        return []

    try:
        logger.info("Initializing MCP client with %d server(s)", len(servers_config))

        # Inject initial OAuth headers for HTTP/SSE server connections.
        initial_oauth_headers = await get_initial_oauth_headers(extensions_config_obj)
        for server_name, auth_header in initial_oauth_headers.items():
            if server_name not in servers_config:
                continue
            if servers_config[server_name].get("transport") in ("sse", "http"):
                existing_headers = dict(servers_config[server_name].get("headers", {}))
                existing_headers["Authorization"] = auth_header
                servers_config[server_name]["headers"] = existing_headers

        tool_interceptors: list[Any] = []
        oauth_interceptor = build_oauth_tool_interceptor(extensions_config_obj)
        if oauth_interceptor is not None:
            tool_interceptors.append(oauth_interceptor)

        # Load custom interceptors declared in extensions_config.json. The
        # schema accepts ``mcpInterceptors`` as either a list of strings
        # (``pkg.module:builder_callable`` — the deer-flow shorthand) or
        # ``McpInterceptorsConfig`` dicts with ``module`` + ``enabled``.
        structured = list(extensions_config_obj.mcp_interceptors or [])
        interceptor_paths: list[str] = [item.module for item in structured if item.enabled]

        # String-form interceptors were coerced into structured entries
        # by ``ExtensionsConfig``'s field validator, so the list above
        # already covers both shapes. Extra dict-like entries from
        # ``model_extra`` are not supported here.

        for interceptor_path in interceptor_paths:
            try:
                builder = _resolve_variable(interceptor_path)
                interceptor = builder() if callable(builder) else builder
                if callable(interceptor):
                    tool_interceptors.append(interceptor)
                    logger.info("Loaded MCP interceptor: %s", interceptor_path)
                elif interceptor is not None:
                    logger.warning(
                        "Builder %s returned non-callable %s; skipping",
                        interceptor_path,
                        type(interceptor).__name__,
                    )
            except Exception as exc:
                logger.warning(
                    "Failed to load MCP interceptor %s: %s",
                    interceptor_path,
                    exc,
                    exc_info=True,
                )

        client = MultiServerMCPClient(
            servers_config,  # type: ignore[arg-type]
            tool_interceptors=tool_interceptors,
            tool_name_prefix=True,
        )

        async def load_server_tools(server_name: str) -> list[BaseTool]:
            try:
                tools = await client.get_tools(server_name=server_name)
                return list(tools)
            except Exception as exc:
                logger.warning(
                    "Skipping MCP server '%s' after tool discovery failed: %s",
                    server_name,
                    exc,
                    exc_info=True,
                )
                return []

        tools_by_server = await asyncio.gather(
            *(load_server_tools(name) for name in servers_config)
        )
        tools = [tool for server_tools in tools_by_server for tool in server_tools]
        logger.info("Successfully loaded %d tool(s) from MCP servers", len(tools))

        wrapped_tools: list[BaseTool] = []
        for tool in tools:
            tool_server: str | None = None
            for name in servers_config:
                if tool.name.startswith(f"{name}_"):
                    tool_server = name
                    break

            if tool_server is not None:
                transport = servers_config[tool_server].get("transport", "stdio")
                if transport == "stdio":
                    wrapped_tools.append(
                        await _make_session_pool_tool(
                            _tag_mcp_tool(tool),
                            tool_server,
                            servers_config[tool_server],
                            tool_interceptors,
                        )
                    )
                else:
                    wrapped_tools.append(_tag_mcp_tool(tool))
            else:
                wrapped_tools.append(_tag_mcp_tool(tool))

        # Patch tools to support sync invocation — needed by deer-flow
        # client streaming paths but cheap insurance even when unused.
        for tool in wrapped_tools:
            if getattr(tool, "func", None) is None and getattr(tool, "coroutine", None) is not None:
                tool.func = make_sync_tool_wrapper(tool.coroutine, tool.name)  # type: ignore[attr-defined]

        return wrapped_tools

    except Exception as exc:
        logger.error("Failed to load MCP tools: %s", exc, exc_info=True)
        return []
