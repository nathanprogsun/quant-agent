"""Subagent execution engine — persistent isolated event loop scaffolding.

Ports deer-flow's subagents/executor.py:148-201 + :204-245 (loop and scheduler
plumbing) — the per-execution ``astream`` / tools / state machine integration
is intentionally kept minimal for P3. Subagents are wired through:

- ``TaskTool`` rewrites (task_tool.py) call ``SubagentExecutor.execute_async``
- The persistent loop guarantees shared async clients (httpx, MCP sessions)
  stay bound to one long-lived loop rather than being recreated per task
- ``atexit`` shuts the loop down cleanly so containers / SIGTERM scenarios
  don't leak the daemon thread
- ``_submit_to_isolated_loop_in_context`` propagates ``ContextVar`` state
  across the thread boundary using ``contextvars.copy_context()`` so tracing
  tokens and settings stay consistent

Filesystem / LLM integration (deferred to subagent_runtime integration tests
in P3-P5 once the loop plumbing is in place).
"""

from __future__ import annotations

import asyncio
import atexit
import logging
import threading
import uuid
from collections.abc import Callable, Coroutine
from concurrent.futures import Future, ThreadPoolExecutor
from contextvars import Context
from datetime import datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class SubagentStatus(Enum):
    """Status of a subagent execution."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"

    @property
    def is_terminal(self) -> bool:
        cls = type(self)
        return self in {cls.COMPLETED, cls.FAILED, cls.CANCELLED, cls.TIMED_OUT}


class SubagentResult:
    """Result holder for background subagent execution.

    Mutation safety: ``try_set_terminal`` is the only way to write terminal
    status / payload fields. The first terminal transition wins; later writes
    from concurrent timeout / cancellation paths are rejected.
    """

    def __init__(
        self,
        task_id: str,
        trace_id: str,
        status: SubagentStatus,
        started_at: datetime | None = None,
    ) -> None:
        self.task_id = task_id
        self.trace_id = trace_id
        self.status = status
        self.started_at = started_at
        self.completed_at: datetime | None = None
        self.result: str | None = None
        self.error: str | None = None
        self.ai_messages: list[dict[str, Any]] = []
        self.token_usage_records: list[dict[str, Any]] = []
        self.usage_reported = False
        self.cancel_event = threading.Event()
        self._state_lock = threading.Lock()

    def try_set_terminal(
        self,
        status: SubagentStatus,
        *,
        result: str | None = None,
        error: str | None = None,
        completed_at: datetime | None = None,
        token_usage_records: list[dict[str, Any]] | None = None,
    ) -> bool:
        """Atomically transition to a terminal status. Returns False if already terminal."""
        if not status.is_terminal:
            raise ValueError(f"Status {status} is not terminal")
        with self._state_lock:
            if self.status.is_terminal:
                return False
            if result is not None:
                self.result = result
            if error is not None:
                self.error = error
            if token_usage_records is not None:
                self.token_usage_records = token_usage_records
            self.completed_at = completed_at or datetime.now()
            self.status = status
            return True


# ---- Module globals — process-lifetime --------------------------------------

_background_tasks: dict[str, SubagentResult] = {}
_background_tasks_lock = threading.Lock()

_scheduler_pool = ThreadPoolExecutor(
    max_workers=3,
    thread_name_prefix="subagent-scheduler-",
)

_isolated_subagent_loop: asyncio.AbstractEventLoop | None = None
_isolated_subagent_loop_thread: threading.Thread | None = None
_isolated_subagent_loop_started: threading.Event | None = None
_isolated_subagent_loop_lock = threading.Lock()


def _run_isolated_subagent_loop(
    loop: asyncio.AbstractEventLoop,
    started_event: threading.Event,
) -> None:
    """Persistent loop body — runs in the daemon thread."""
    asyncio.set_event_loop(loop)
    loop.call_soon(started_event.set)
    try:
        loop.run_forever()
    finally:
        started_event.clear()


def _shutdown_isolated_subagent_loop() -> None:
    """Stop and close the persistent isolated subagent event loop."""
    global _isolated_subagent_loop, _isolated_subagent_loop_thread, _isolated_subagent_loop_started

    with _isolated_subagent_loop_lock:
        loop = _isolated_subagent_loop
        thread = _isolated_subagent_loop_thread
        _isolated_subagent_loop = None
        _isolated_subagent_loop_thread = None
        _isolated_subagent_loop_started = None

    if loop is None:
        return

    if loop.is_running():
        loop.call_soon_threadsafe(loop.stop)

    if thread is not None and thread.is_alive() and thread is not threading.current_thread():
        thread.join(timeout=1)

    thread_stopped = thread is None or not thread.is_alive()
    loop_stopped = not loop.is_running()

    if not loop.is_closed():
        if thread_stopped and loop_stopped:
            loop.close()
        else:
            logger.warning(
                "Skipping close of isolated subagent loop because shutdown did not complete (thread_alive=%s, loop_running=%s)",
                thread is not None and thread.is_alive(),
                loop.is_running(),
            )


atexit.register(_shutdown_isolated_subagent_loop)


def _get_isolated_subagent_loop() -> asyncio.AbstractEventLoop:
    """Return the persistent event loop for subagent executions (lazily created)."""
    global _isolated_subagent_loop, _isolated_subagent_loop_thread, _isolated_subagent_loop_started
    with _isolated_subagent_loop_lock:
        thread_is_alive = (
            _isolated_subagent_loop_thread is not None and _isolated_subagent_loop_thread.is_alive()
        )
        loop_is_usable = (
            _isolated_subagent_loop is not None
            and not _isolated_subagent_loop.is_closed()
            and _isolated_subagent_loop.is_running()
            and thread_is_alive
        )

        if not loop_is_usable:
            loop = asyncio.new_event_loop()
            started_event = threading.Event()
            thread = threading.Thread(
                target=_run_isolated_subagent_loop,
                args=(loop, started_event),
                name="subagent-persistent-loop",
                daemon=True,
            )
            thread.start()
            if not started_event.wait(timeout=5):
                loop.call_soon_threadsafe(loop.stop)
                thread.join(timeout=1)
                loop.close()
                raise RuntimeError("Timed out starting isolated subagent event loop")
            _isolated_subagent_loop = loop
            _isolated_subagent_loop_thread = thread
            _isolated_subagent_loop_started = started_event

    if _isolated_subagent_loop is None:
        raise RuntimeError("Isolated subagent event loop is not initialized")
    return _isolated_subagent_loop


def _submit_to_isolated_loop_in_context(
    context: Context,
    coro_factory: Callable[[], Coroutine[Any, Any, Any]],
) -> Future[Any]:
    """Submit a coroutine to the isolated loop while preserving ContextVar state."""
    return context.run(
        lambda: asyncio.run_coroutine_threadsafe(
            coro_factory(),
            _get_isolated_subagent_loop(),
        )
    )


def request_cancel_background_task(task_id: str) -> None:
    """Signal a running background task to stop cooperatively."""
    with _background_tasks_lock:
        result = _background_tasks.get(task_id)
        if result is not None:
            result.cancel_event.set()
            logger.info("Requested cancellation for background task %s", task_id)


def get_background_task_result(task_id: str) -> SubagentResult | None:
    """Get a background task result by id."""
    with _background_tasks_lock:
        return _background_tasks.get(task_id)


def list_background_tasks() -> list[SubagentResult]:
    """List all known background tasks."""
    with _background_tasks_lock:
        return list(_background_tasks.values())


def cleanup_background_task(task_id: str) -> None:
    """Remove a completed task from background tasks. Only removes terminal tasks."""
    with _background_tasks_lock:
        result = _background_tasks.get(task_id)
        if result is None:
            return
        if result.status.is_terminal or result.completed_at is not None:
            del _background_tasks[task_id]
        else:
            logger.debug(
                "Skipping cleanup for non-terminal background task %s (status=%s)",
                task_id,
                result.status.value,
            )


MAX_CONCURRENT_SUBAGENTS = 3


class SubagentExecutor:
    """Executor for running subagents via the persistent isolated loop."""

    def __init__(
        self,
        *,
        name: str,
        prompt: str,
        timeout_seconds: int = 1800,
        max_turns: int | None = None,
        trace_id: str | None = None,
    ) -> None:
        """Initialize the executor.

        Args:
            name: Subagent name (e.g. "general-purpose").
            prompt: Initial task description for the subagent.
            timeout_seconds: Wall-clock timeout (default 1800 = 30 min).
            max_turns: Optional turn limit (None = inherit / unbounded).
            trace_id: Optional trace id; auto-generated if absent.
        """
        self.name = name
        self.prompt = prompt
        self.timeout_seconds = timeout_seconds
        self.max_turns = max_turns
        self.trace_id = trace_id or str(uuid.uuid4())[:8]

    def execute_async(self, task: str, task_id: str | None = None) -> str:
        """Schedule a background subagent execution on the persistent isolated loop.

        Returns the task_id. The TaskTool polls ``get_background_task_result``
        for terminal status; this method does not block the caller.
        """
        if task_id is None:
            task_id = str(uuid.uuid4())[:8]
        result = SubagentResult(
            task_id=task_id,
            trace_id=self.trace_id,
            status=SubagentStatus.PENDING,
        )
        with _background_tasks_lock:
            _background_tasks[task_id] = result
        logger.info(
            "[trace=%s] Subagent %s scheduled, task_id=%s, timeout=%ss",
            self.trace_id,
            self.name,
            task_id,
            self.timeout_seconds,
        )
        # Scheduling only — actual execution deferred to P3 subagent-runtime
        # integration once the persistent loop is validated.
        return task_id

    def _run_task(self, task: str, task_id: str) -> SubagentResult:
        """Run a subagent on the persistent loop. Used internally by future runtime paths."""
        with _background_tasks_lock:
            holder = _background_tasks.get(task_id)
            if holder is None:
                holder = SubagentResult(
                    task_id=task_id,
                    trace_id=self.trace_id,
                    status=SubagentStatus.RUNNING,
                    started_at=datetime.now(),
                )
                _background_tasks[task_id] = holder
            else:
                holder.status = SubagentStatus.RUNNING
                holder.started_at = datetime.now()
        try:
            asyncio.run_coroutine_threadsafe(
                self._aexecute_placeholder(task, holder),
                _get_isolated_subagent_loop(),
            ).result(timeout=self.timeout_seconds)
        except Exception as exc:
            holder.try_set_terminal(SubagentStatus.FAILED, error=str(exc))
        return holder

    async def _aexecute_placeholder(self, task: str, holder: SubagentResult) -> None:
        """Placeholder async body. Real astream / LLM run is added in later subagent-runtime tasks."""
        await asyncio.sleep(0)
        holder.try_set_terminal(SubagentStatus.COMPLETED, result=f"echo:{task}")
