"""Persistent MCP session pool — owner-task lifecycle.

Ports ``deerflow.mcp.session_pool`` (lines 84-456). Required so stateful
MCP servers (Playwright, filesystem watchers, …) keep their server-side
state across calls within the same thread.

The single most important invariant: anyio cancel scopes must be entered
and exited by the *same task*. We satisfy that by owning each pooled
session inside a dedicated ``_run_session`` task which enters the
context manager, hands the live session back via ``ready``, and then
blocks on ``close_evt``. Every shutdown path signals and waits — only
the owner task itself runs ``__aexit__``.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import threading
from collections import OrderedDict
from typing import Any

from mcp import ClientSession

logger = logging.getLogger(__name__)


class MCPSessionPool:
    """Pool of persistent MCP sessions, keyed by ``(server_name, scope_key)``."""

    MAX_SESSIONS = 256
    SESSION_CLOSE_TIMEOUT = 5.0

    def __init__(self) -> None:
        # Each entry: (session, owning_loop, owner_task, close_event).
        self._entries: OrderedDict[
            tuple[str, str],
            tuple[ClientSession, asyncio.AbstractEventLoop, asyncio.Task[Any], asyncio.Event],
        ] = OrderedDict()
        # In-flight creations, keyed by (server, scope). Lets concurrent callers
        # on the same loop share a single creation instead of each spawning
        # a duplicate session.
        self._inflight: dict[
            tuple[str, str],
            tuple[
                asyncio.AbstractEventLoop,
                asyncio.Future[ClientSession],
                asyncio.Task[Any],
                asyncio.Event,
            ],
        ] = {}
        # threading.Lock is not bound to any event loop, so it is safe to
        # acquire from both async paths and sync/worker-thread paths.
        self._lock = threading.Lock()

    # ── owner task ──────────────────────────────────────────────

    async def _run_session(
        self,
        connection: dict[str, Any],
        ready: asyncio.Future[ClientSession],
        close_evt: asyncio.Event,
    ) -> None:
        """Own a single MCP session for its entire lifetime."""
        from langchain_mcp_adapters.sessions import create_session

        # ``connection`` is a dict of transport-specific fields. The langchain
        # adapter's typed signature accepts a discriminated union; cast to
        # ``Any`` here because the upstream type narrows on ``transport`` in
        # a way mypy can't follow.
        cm = create_session(connection)
        try:
            session = await cm.__aenter__()
        except BaseException as exc:
            if not ready.done():
                ready.set_exception(exc)
            return

        try:
            await session.initialize()
            if not ready.done():
                ready.set_result(session)
            await close_evt.wait()
        except BaseException as exc:
            if not ready.done():
                ready.set_exception(exc)
        finally:
            try:
                await cm.__aexit__(None, None, None)
            except Exception:
                logger.warning("Error closing MCP session", exc_info=True)

    async def get_session(
        self,
        server_name: str,
        scope_key: str,
        connection: dict[str, Any],
    ) -> ClientSession:
        """Return an initialized persistent session, creating one if necessary."""
        key = (server_name, scope_key)
        current_loop = asyncio.get_running_loop()

        evicted: list[tuple[asyncio.AbstractEventLoop, asyncio.Task[Any], asyncio.Event, bool]] = []
        join: asyncio.Future[ClientSession] | None = None
        ready: asyncio.Future[ClientSession] | None = None
        close_evt: asyncio.Event | None = None
        task: asyncio.Task[Any] | None = None

        # Phase 1: inspect/mutate the registry under the lock (no awaits).
        with self._lock:
            if key in self._entries:
                entry = self._entries[key]
                ent_session, loop, ent_task, ent_close = entry
                if loop is current_loop and not loop.is_closed():
                    self._entries.move_to_end(key)
                    return ent_session
                self._entries.pop(key)
                evicted.append((loop, ent_task, ent_close, False))

            inflight = self._inflight.get(key)
            if inflight is not None and inflight[0] is current_loop and not inflight[0].is_closed():
                join = inflight[1]
            else:
                if inflight is not None:
                    self._inflight.pop(key)
                    evicted.append((inflight[0], inflight[2], inflight[3], True))
                ready = current_loop.create_future()
                close_evt = asyncio.Event()
                task = current_loop.create_task(self._run_session(connection, ready, close_evt))
                self._inflight[key] = (current_loop, ready, task, close_evt)

            while len(self._entries) >= self.MAX_SESSIONS:
                oldest_key, (_, loop, ent_task, ent_close) = next(iter(self._entries.items()))
                self._entries.pop(oldest_key)
                evicted.append((loop, ent_task, ent_close, False))

        # Phase 2: shut down evicted sessions.
        for loop, ent_task, ent_close, cancel in evicted:
            if loop is current_loop and not loop.is_closed():
                await self._shutdown(ent_close, ent_task, cancel)
            elif cancel:
                await self._shutdown_entry(loop, ent_task, ent_close, cancel=True)
            else:
                self._signal_close(loop, ent_close)

        # Phase 2b: concurrent creator — share its result.
        if join is not None:
            return await asyncio.shield(join)

        assert ready is not None and close_evt is not None and task is not None

        # Phase 3: wait for the owner task to publish the initialized session.
        try:
            session = await asyncio.shield(ready)
        except BaseException:
            owner_already_failed = (
                ready.done() and not ready.cancelled() and ready.exception() is not None
            )
            if not owner_already_failed:
                close_evt.set()
                task.cancel()
            try:
                await asyncio.shield(task)
            except BaseException:
                logger.debug("Owner task ended during get_session unwind", exc_info=True)
            with self._lock:
                if self._inflight.get(key) == (current_loop, ready, task, close_evt):
                    self._inflight.pop(key)
            raise

        # Phase 4: promote in-flight to registered, only if it's still ours.
        with self._lock:
            still_ours = self._inflight.get(key) == (current_loop, ready, task, close_evt)
            if still_ours:
                self._inflight.pop(key)
                self._entries[key] = (session, current_loop, task, close_evt)
        if not still_ours:
            await self._shutdown(close_evt, task)
            raise asyncio.CancelledError(
                "MCP session pool was closed while the session was being created"
            )
        logger.info("Created persistent MCP session for %s/%s", server_name, scope_key)
        return session

    # ── cleanup helpers ─────────────────────────────────────────

    @staticmethod
    def _signal_close(loop: asyncio.AbstractEventLoop, close_evt: asyncio.Event) -> None:
        if loop.is_closed():
            return
        with contextlib.suppress(RuntimeError):
            loop.call_soon_threadsafe(close_evt.set)

    async def _shutdown(
        self,
        close_evt: asyncio.Event,
        task: asyncio.Task[Any],
        cancel: bool = False,
    ) -> None:
        close_evt.set()
        if cancel:
            task.cancel()
        try:
            await task
        except (Exception, asyncio.CancelledError):
            logger.debug("Owner task ended during shutdown", exc_info=True)

    async def _shutdown_entry(
        self,
        loop: asyncio.AbstractEventLoop,
        task: asyncio.Task[Any],
        close_evt: asyncio.Event,
        cancel: bool = False,
    ) -> None:
        if loop.is_closed():
            return
        current_loop = asyncio.get_running_loop()
        if loop is current_loop:
            await self._shutdown(close_evt, task, cancel)
        elif loop.is_running():
            future = asyncio.run_coroutine_threadsafe(self._shutdown(close_evt, task, cancel), loop)
            try:
                await asyncio.wrap_future(future)
            except Exception:
                logger.warning("Error closing MCP session on owning loop", exc_info=True)
        else:
            logger.warning(
                "Owning loop for MCP session is idle; signalling close best-effort. "
                "Session may leak until the loop runs again."
            )
            self._signal_close(loop, close_evt)
            if cancel:
                with contextlib.suppress(RuntimeError):
                    loop.call_soon_threadsafe(task.cancel)

    async def close_scope(self, scope_key: str) -> None:
        with self._lock:
            keys = [k for k in self._entries if k[1] == scope_key]
            entries = [self._entries.pop(k) for k in keys]
            inflight_keys = [k for k in self._inflight if k[1] == scope_key]
            inflight = [self._inflight.pop(k) for k in inflight_keys]
        for _session, loop, task, close_evt in entries:
            await self._shutdown_entry(loop, task, close_evt)
        for loop, _ready, task, close_evt in inflight:
            await self._shutdown_entry(loop, task, close_evt, cancel=True)

    async def close_server(self, server_name: str) -> None:
        with self._lock:
            keys = [k for k in self._entries if k[0] == server_name]
            entries = [self._entries.pop(k) for k in keys]
            inflight_keys = [k for k in self._inflight if k[0] == server_name]
            inflight = [self._inflight.pop(k) for k in inflight_keys]
        for _session, loop, task, close_evt in entries:
            await self._shutdown_entry(loop, task, close_evt)
        for loop, _ready, task, close_evt in inflight:
            await self._shutdown_entry(loop, task, close_evt, cancel=True)

    async def close_all(self) -> None:
        with self._lock:
            entries = list(self._entries.values())
            self._entries.clear()
            inflight = list(self._inflight.values())
            self._inflight.clear()
        for _session, loop, task, close_evt in entries:
            await self._shutdown_entry(loop, task, close_evt)
        for loop, _ready, task, close_evt in inflight:
            await self._shutdown_entry(loop, task, close_evt, cancel=True)

    def close_all_sync(self) -> None:
        """Synchronously close every session by signalling its owner task.

        Each owner task tears down on the loop that owns it. Safe to call
        from any thread that does not already own the running loop; from a
        running loop we only *signal* (the caller must yield control).
        """
        with self._lock:
            entries = list(self._entries.values())
            self._entries.clear()
            inflight = list(self._inflight.values())
            self._inflight.clear()

        owners = [(loop, task, close_evt, False) for _s, loop, task, close_evt in entries]
        owners += [(loop, task, close_evt, True) for loop, _r, task, close_evt in inflight]
        try:
            current_running_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_running_loop = None
        for loop, task, close_evt, cancel in owners:
            if loop.is_closed():
                continue
            try:
                if loop is current_running_loop:
                    close_evt.set()
                    if cancel:
                        task.cancel()
                elif loop.is_running():
                    future = asyncio.run_coroutine_threadsafe(
                        self._shutdown(close_evt, task, cancel), loop
                    )
                    future.result(timeout=self.SESSION_CLOSE_TIMEOUT)
                else:
                    loop.run_until_complete(self._shutdown(close_evt, task, cancel))
            except Exception:
                logger.debug("Error closing MCP session during sync close", exc_info=True)


# ── module-level singleton ──────────────────────────────────────

_pool: MCPSessionPool | None = None
_pool_lock = threading.Lock()


def get_session_pool() -> MCPSessionPool:
    """Return the global session-pool singleton."""
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                _pool = MCPSessionPool()
    return _pool


def reset_session_pool() -> None:
    """Reset the singleton (for tests)."""
    global _pool
    _pool = None
