"""Sync wrapper for async LangChain tools.

Port of ``deerflow.tools.sync``. Runs the coroutine on a shared background
thread when called from inside a running event loop, so an MCP-tool call
from a sync code path does not deadlock. The same thread pool backs all
sync wrappers; ``atexit`` shuts it down without waiting (close enough —
daemon workers).
"""

from __future__ import annotations

import asyncio
import atexit
import concurrent.futures
import contextvars
import logging
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

_SYNC_TOOL_EXECUTOR = concurrent.futures.ThreadPoolExecutor(
    max_workers=10, thread_name_prefix="tool-sync"
)
atexit.register(lambda: _SYNC_TOOL_EXECUTOR.shutdown(wait=False))


def make_sync_tool_wrapper(coro: Callable[..., Any], tool_name: str) -> Callable[..., Any]:
    """Build a synchronous wrapper for an async tool coroutine.

    If called from a sync context the coroutine is awaited directly via
    ``asyncio.run``; if called from a running loop the call is forwarded
    to the shared thread pool with a copied ``ContextVar`` context so
    caller-scope logging / tracing context survives the hop.
    """

    def run_coroutine(*args: Any, **kwargs: Any) -> Any:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        try:
            if loop is not None and loop.is_running():
                ctx = contextvars.copy_context()
                future = _SYNC_TOOL_EXECUTOR.submit(
                    ctx.run, lambda: asyncio.run(coro(*args, **kwargs))
                )
                return future.result()
            return asyncio.run(coro(*args, **kwargs))
        except Exception as exc:
            logger.error(
                "Error invoking tool %r via sync wrapper: %s",
                tool_name,
                exc,
                exc_info=True,
            )
            raise

    return run_coroutine
