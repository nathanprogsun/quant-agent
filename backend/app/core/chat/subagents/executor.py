"""Subagent execution engine — real astream/LLM run path.

Ports deer-flow's subagents/executor.py:148-201 (loop plumbing), :204-245
(scheduler pool), and the body of execute_async / _aexecute which drive the
real ``graph.astream(...)`` -> ``get_stream_writer()`` flow.

Subagent runtime:
- Each ``SubagentExecutor.execute_async`` call schedules a background task
  on the persistent isolated loop (3.1) with cooperative cancellation via
  ``SubagentResult.cancel_event``.
- The graph is built with ``checkpointer=False`` (3.3) so a parent
  checkpointer cannot leak into the subagent's state.
- ``SubagentTokenCollector`` (3.4) is registered as a callback so each LLM
  end yields one usage record (deduped by ``run_id``).
- Stream events tagged by ``task_id`` are emitted via
  ``langgraph.config.get_stream_writer()`` so the parent TaskTool can
  forward ``task_started`` / ``task_running`` / ``task_completed`` /
  ``task_failed`` to its own stream consumer.
"""

from __future__ import annotations

import asyncio
import atexit
import contextlib
import logging
import threading
import uuid
from collections.abc import Callable, Coroutine
from concurrent.futures import Future, ThreadPoolExecutor
from contextvars import Context
from datetime import datetime
from enum import Enum
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.config import get_stream_writer
from langgraph.graph import END, StateGraph
from pydantic import SecretStr

from app.core.chat.agent.thread_state import ThreadState
from app.core.chat.subagents.token_collector import SubagentTokenCollector
from app.settings import get_settings

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


# ---- Subagent model resolution --------------------------------------------

# Default subagent system prompt — overridable per-executor for custom agents.
DEFAULT_SUBAGENT_SYSTEM_PROMPT = (
    "You are a subagent delegated by a parent agent. Complete the given task "
    "concisely and return only the result. Do not call tools unless necessary."
)


def _resolve_subagent_model() -> ChatOpenAI:
    """Build the subagent's ChatOpenAI model from global settings.

    Uses the same factory shape as ``lead_agent.make_lead_agent`` so the
    subagent and lead agent share provider configuration. Tests can monkeypatch
    the ``ChatOpenAI`` symbol imported by this module to substitute a fake.
    """
    settings = get_settings()
    return ChatOpenAI(
        model=settings.model,
        api_key=SecretStr(settings.openai_api_key.get_secret_value()),
        base_url=settings.openai_base_url,
        streaming=True,
        extra_body={"reasoning_split": True},
    )


# ---- checkpointer=False enforcement (P3.3) ---------------------------------

# quant-agent does not use ``langchain.agents.create_agent``; subagents are
# built with a manual ``StateGraph(...).compile(checkpointer=...)``. We
# isolate subagent state by hardcoding ``checkpointer=False`` here so a
# parent checkpointer cannot accidentally leak into the subagent graph
# (which would inherit permission/state).
_PARENT_CHECKPOINTER_MSG = (
    "Subagents must be compiled with checkpointer=False; passing a parent "
    "checkpointer would let subagent writes leak into the parent thread's "
    "state. See P3.3 in docs/superpowers/plans/2026-06-30-p0-p4-...md."
)


def _extract_ai_text(message: Any) -> str | None:
    """Best-effort text extraction from an AI message for streaming events.

    Handles str content, list-of-blocks content (text parts), and falls back
    to ``str(message.content)`` for any other shape.
    """
    content = getattr(message, "content", None)
    if content is None:
        return None
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                text_val = block.get("text")
                if isinstance(text_val, str):
                    parts.append(text_val)
        return "".join(parts) if parts else None
    return str(content)


def _build_subagent_state_graph(model_name: str) -> tuple[Any, ChatOpenAI]:
    """Build a minimal real StateGraph for a subagent.

    The graph is a single ``model`` node that invokes the resolved model
    and returns its response as a state delta. P3.6+ layers middlewares /
    tools onto this base; for now the contract under test is that
    ``compile()`` is invoked with ``checkpointer=False`` and the model is
    resolved from settings rather than a hardcoded placeholder key.

    Args:
        model_name: Resolved model name; passed through for parity with
            the previous helper signature but the actual factory call uses
            the live ``get_settings()`` so the subagent inherits the same
            provider as the lead agent.

    Returns:
        ``(graph, model)`` tuple — the uncompiled ``StateGraph`` plus the
        ``ChatOpenAI`` model bound to it.
    """
    _ = model_name  # settings owns the live model resolution
    model = _resolve_subagent_model()
    graph = StateGraph(ThreadState)

    async def model_node(state: ThreadState) -> dict[str, Any]:
        """Invoke the model with the current message list and return the AIMessage."""
        messages = list(state.get("messages", []))
        if not messages:
            return {"messages": [AIMessage(content="No input provided to subagent.")]}
        # Ensure system prompt precedes the task
        if not any(isinstance(m, SystemMessage) for m in messages):
            messages = [SystemMessage(content=DEFAULT_SUBAGENT_SYSTEM_PROMPT), *messages]
        response = await model.ainvoke(messages)
        return {"messages": [response]}

    graph.add_node("model", model_node)
    graph.set_entry_point("model")
    graph.add_edge("model", END)
    return graph, model


def compile_subagent_graph(
    *,
    model_name: str,
    checkpointer: Any = None,
) -> Any:
    """Compile a subagent graph with ``checkpointer=False`` enforced.

    Adapted from deer-flow's executor.py:375 — the hazard documented there
    is that a parent checkpointer silently inherits into the subagent graph.
    This guard makes the regression loud.

    Args:
        model_name: Resolved model for the subagent (passed through for API
            parity; the live factory uses ``get_settings()``).
        checkpointer: If non-None, raises ``NotImplementedError``. Subagents
            always compile with ``checkpointer=False``.

    Returns:
        The compiled subagent graph (a ``CompiledStateGraph``).
    """
    if checkpointer is not None:
        raise NotImplementedError(_PARENT_CHECKPOINTER_MSG)

    graph, _model = _build_subagent_state_graph(model_name)
    return graph.compile(checkpointer=False)


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
        system_prompt: str | None = None,
    ) -> None:
        """Initialize the executor.

        Args:
            name: Subagent name (e.g. "general-purpose").
            prompt: Initial task description for the subagent.
            timeout_seconds: Wall-clock timeout (default 1800 = 30 min).
            max_turns: Optional turn limit (None = inherit / unbounded).
            trace_id: Optional trace id; auto-generated if absent.
            system_prompt: Optional per-subagent system prompt override.
        """
        self.name = name
        self.prompt = prompt
        self.timeout_seconds = timeout_seconds
        self.max_turns = max_turns
        self.trace_id = trace_id or str(uuid.uuid4())[:8]
        self.system_prompt = system_prompt or DEFAULT_SUBAGENT_SYSTEM_PROMPT

    def execute_async(self, task: str, task_id: str | None = None) -> str:
        """Schedule a background subagent execution on the persistent isolated loop.

        Returns the ``task_id``. The TaskTool polls ``get_background_task_result``
        for terminal status; this method does not block the caller.

        The actual astream/LLM run is performed on the persistent isolated loop
        by ``_run_task`` (see ``_aexecute`` for the async body).
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

        # Schedule the real astream/LLM run on the persistent isolated loop.
        # The submission is best-effort: if the loop is shut down (test
        # teardown), fall through and let the holder sit in PENDING.
        try:
            loop = _get_isolated_subagent_loop()
            future = asyncio.run_coroutine_threadsafe(
                self._aexecute(task, result),
                loop,
            )
            # Watchdog: surface timeout / exception in the holder once the
            # future resolves. ``run_task_watchdog`` runs in a daemon thread
            # so it does not block the caller of execute_async.
            threading.Thread(
                target=self._run_task_watchdog,
                args=(task_id, future),
                name=f"subagent-watchdog-{task_id}",
                daemon=True,
            ).start()
        except Exception as exc:  # pragma: no cover — defensive
            logger.exception("[trace=%s] Subagent %s failed to schedule", self.trace_id, self.name)
            result.try_set_terminal(SubagentStatus.FAILED, error=str(exc))

        return task_id

    def _run_task_watchdog(self, task_id: str, future: Future[Any]) -> None:
        """Wait for the isolated-loop future and reflect terminal state into the holder.

        Cancellation is signalled via ``SubagentResult.cancel_event`` — this
        watchdog translates ``CancelledError`` / ``TimeoutError`` from the
        future into a CANCELLED / TIMED_OUT terminal transition.
        """
        try:
            future.result(timeout=self.timeout_seconds)
        except TimeoutError:
            holder = get_background_task_result(task_id)
            if holder is not None:
                holder.cancel_event.set()
                holder.try_set_terminal(
                    SubagentStatus.TIMED_OUT,
                    error=f"Execution timed out after {self.timeout_seconds} seconds",
                )
            future.cancel()
        except asyncio.CancelledError:
            holder = get_background_task_result(task_id)
            if holder is not None:
                holder.try_set_terminal(
                    SubagentStatus.CANCELLED,
                    error="Cancelled by parent",
                )
        except Exception as exc:
            holder = get_background_task_result(task_id)
            if holder is not None and not holder.status.is_terminal:
                holder.try_set_terminal(
                    SubagentStatus.FAILED,
                    error=str(exc),
                )

    async def _aexecute(self, task: str, holder: SubagentResult) -> None:
        """Real astream / LLM run.

        Builds the subagent graph, opens a stream writer, collects token
        usage via ``SubagentTokenCollector``, and writes ``task_running`` /
        ``task_completed`` / ``task_failed`` events tagged with the
        ``task_id``. Honours ``holder.cancel_event`` at every astream
        iteration boundary.
        """
        # Pre-check: bail out immediately if already cancelled
        if holder.cancel_event.is_set():
            logger.info(
                "[trace=%s] Subagent %s cancelled before streaming", self.trace_id, self.name
            )
            holder.try_set_terminal(
                SubagentStatus.CANCELLED,
                error="Cancelled by parent",
            )
            return

        # Acquire a stream writer for this execution. ``get_stream_writer``
        # returns a no-op outside an active langgraph stream — callers can
        # still rely on the holder's ``result`` field for terminal state.
        try:
            writer = get_stream_writer()
        except Exception:
            writer = None

        if writer is not None:
            try:
                writer({"type": "task_running", "task_id": holder.task_id, "status": "starting"})
            except Exception:  # pragma: no cover — defensive
                logger.debug("task_running writer failed", exc_info=True)

        # Build the subagent graph + token collector
        try:
            compiled = compile_subagent_graph(model_name=get_settings().model)
        except NotImplementedError:
            raise
        except Exception as exc:
            logger.exception(
                "[trace=%s] Subagent %s failed to compile graph", self.trace_id, self.name
            )
            holder.try_set_terminal(
                SubagentStatus.FAILED,
                error=f"Failed to compile subagent graph: {exc}",
            )
            return

        collector = SubagentTokenCollector(caller=f"subagent:{self.name}")

        # Initial state — system prompt + human task. Mirror deer-flow's
        # _build_initial_state shape (executor.py:485-490) so a downstream
        # tool-binding upgrade slots in without a state-shape rewrite.
        state: dict[str, Any] = {
            "messages": [
                SystemMessage(content=self.system_prompt),
                HumanMessage(content=task),
            ],
        }

        run_config: dict[str, Any] = {
            "recursion_limit": self.max_turns if self.max_turns is not None else 25,
            "callbacks": [collector],
            "tags": [f"subagent:{self.name}"],
        }

        try:
            final_chunk: dict[str, Any] | None = None
            seen_message_ids: set[str] = set()

            async for chunk in compiled.astream(state, config=run_config, stream_mode="values"):
                if holder.cancel_event.is_set():
                    logger.info(
                        "[trace=%s] Subagent %s cancelled mid-stream", self.trace_id, self.name
                    )
                    holder.try_set_terminal(
                        SubagentStatus.CANCELLED,
                        error="Cancelled by parent",
                        token_usage_records=collector.snapshot_records(),
                    )
                    if writer is not None:
                        with contextlib.suppress(Exception):
                            writer({"type": "task_cancelled", "task_id": holder.task_id})
                    return

                final_chunk = chunk
                messages = chunk.get("messages", []) if isinstance(chunk, dict) else []
                if messages:
                    last_message = messages[-1]
                    if isinstance(last_message, AIMessage):
                        message_id = getattr(last_message, "id", None)
                        if message_id and message_id in seen_message_ids:
                            continue
                        if message_id:
                            seen_message_ids.add(message_id)
                        payload = last_message.model_dump()
                        holder.ai_messages.append(payload)
                        if writer is not None:
                            try:
                                writer(
                                    {
                                        "type": "task_running",
                                        "task_id": holder.task_id,
                                        "message": payload,
                                        "message_index": len(holder.ai_messages),
                                    }
                                )
                            except Exception:  # pragma: no cover
                                logger.debug("task_running writer failed", exc_info=True)

            # Extract final result text from the last AI message
            final_text: str | None = None
            if final_chunk and isinstance(final_chunk, dict):
                final_messages = final_chunk.get("messages", [])
                for msg in reversed(final_messages):
                    if isinstance(msg, AIMessage):
                        final_text = _extract_ai_text(msg)
                        if final_text:
                            break

            if final_text is None:
                # Fallback: concatenate all captured AI message texts
                texts = [_extract_ai_text(m) for m in (holder.ai_messages or [])]
                texts_str: list[str] = [t for t in texts if isinstance(t, str)]
                final_text = "\n".join(texts_str) if texts_str else "No response generated"

            holder.try_set_terminal(
                SubagentStatus.COMPLETED,
                result=final_text,
                token_usage_records=collector.snapshot_records(),
            )

            if writer is not None:
                try:
                    writer(
                        {
                            "type": "task_completed",
                            "task_id": holder.task_id,
                            "result": final_text,
                            "usage": collector.snapshot_records(),
                        }
                    )
                except Exception:  # pragma: no cover
                    logger.debug("task_completed writer failed", exc_info=True)
        except Exception as exc:
            logger.exception(
                "[trace=%s] Subagent %s failed during execution", self.trace_id, self.name
            )
            holder.try_set_terminal(
                SubagentStatus.FAILED,
                error=str(exc),
                token_usage_records=collector.snapshot_records(),
            )
            if writer is not None:
                with contextlib.suppress(Exception):
                    writer({"type": "task_failed", "task_id": holder.task_id, "error": str(exc)})
