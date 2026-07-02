"""In-memory cache of MCP tools resolved by langchain-mcp-adapters.

Lazy on first call so tests + LangGraph Studio paths work without forcing
all transports to initialise at import time. ``initialize_mcp_tools`` is
the explicit, awaited entry point used by FastAPI ``lifespan`` startup.

Also tracks the source ``extensions_config.json`` mtime so a runtime
write (via the REST API) invalidates the cache on next access.
"""

from __future__ import annotations

import asyncio
import logging
import os

from langchain_core.tools import BaseTool

from app.util.asyncio_util.adapter import run_in_pool

logger = logging.getLogger(__name__)

_mcp_tools_cache: list[BaseTool] | None = None
_cache_initialized: bool = False
_initialization_lock = asyncio.Lock()
_config_mtime: float | None = None


def _get_config_mtime() -> float | None:
    """Return the on-disk mtime of ``extensions_config.json`` (or ``None``)."""
    from app.config.extensions_config import ExtensionsConfig

    config_path = ExtensionsConfig.resolve_config_path()
    if config_path and config_path.exists():
        return os.path.getmtime(config_path)
    return None


def _is_cache_stale() -> bool:
    """True iff the source file changed since the cache was primed."""
    global _config_mtime

    if not _cache_initialized:
        return False

    current_mtime = _get_config_mtime()
    if _config_mtime is None or current_mtime is None:
        return False
    if current_mtime > _config_mtime:
        logger.info(
            "MCP config file has been modified (mtime: %s -> %s), cache is stale",
            _config_mtime,
            current_mtime,
        )
        return True
    return False


async def initialize_mcp_tools() -> list[BaseTool]:
    """Initialise and cache MCP tools. Single-call guarded by an asyncio lock.

    Intended as the startup hook in :mod:`app.web.lifespan`. Re-uses an
    existing cache entry when present so repeated calls are O(1).
    """
    global _mcp_tools_cache, _cache_initialized, _config_mtime

    async with _initialization_lock:
        if _cache_initialized:
            logger.info("MCP tools already initialized")
            return _mcp_tools_cache or []

        from app.mcp.tools import get_mcp_tools

        logger.info("Initializing MCP tools...")
        _mcp_tools_cache = await get_mcp_tools()
        _cache_initialized = True
        _config_mtime = _get_config_mtime()
        logger.info(
            "MCP tools initialized: %d tool(s) loaded (config mtime: %s)",
            len(_mcp_tools_cache),
            _config_mtime,
        )
        return _mcp_tools_cache


def get_cached_mcp_tools() -> list[BaseTool]:
    """Return the cached MCP tool list, lazily initialising if needed.

    Safe to call from any thread. If a loop is already running on this
    thread the cache is initialised via a one-shot thread pool to avoid
    the ``asyncio.run()`` inside-running-loop error.
    """
    global _cache_initialized

    if _is_cache_stale():
        logger.info("MCP cache is stale, resetting for re-initialization...")
        reset_mcp_tools_cache()

    if _cache_initialized:
        return _mcp_tools_cache or []

    logger.info("MCP tools not initialized, performing lazy initialization...")
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(asyncio.run, initialize_mcp_tools())
                future.result()
        else:
            loop.run_until_complete(initialize_mcp_tools())
    except RuntimeError:
        try:
            asyncio.run(initialize_mcp_tools())
        except Exception:
            logger.exception("Failed to lazy-initialize MCP tools")
            return []
    except Exception:
        logger.exception("Failed to lazy-initialize MCP tools")
        return []

    return _mcp_tools_cache or []


async def get_cached_mcp_tools_async() -> list[BaseTool]:
    """Return the cached MCP tool list via thread pool to avoid blocking."""
    return await run_in_pool(get_cached_mcp_tools)


def reset_mcp_tools_cache() -> None:
    """Clear the in-memory cache + close persistent MCP sessions."""
    global _mcp_tools_cache, _cache_initialized, _config_mtime
    _mcp_tools_cache = None
    _cache_initialized = False
    _config_mtime = None

    try:
        from app.mcp.session_pool import get_session_pool

        get_session_pool().close_all_sync()
    except Exception:
        logger.debug("Could not close MCP session pool on cache reset", exc_info=True)

    from app.mcp.session_pool import reset_session_pool

    reset_session_pool()
    logger.info("MCP tools cache reset")
