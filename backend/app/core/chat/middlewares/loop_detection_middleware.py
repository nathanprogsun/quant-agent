"""Middleware to detect and break repetitive tool call loops.

Ported from deer-flow loop_detection_middleware.py:477-593.
Adapted: before_agent/after_agent → abefore_model/aafter_model (D1).
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
from collections import OrderedDict, defaultdict
from collections.abc import Awaitable, Callable
from copy import deepcopy
from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import HumanMessage
from langgraph.runtime import Runtime

logger = logging.getLogger(__name__)

_DEFAULT_WARN_THRESHOLD = 3
_DEFAULT_HARD_LIMIT = 5
_DEFAULT_WINDOW_SIZE = 20
_DEFAULT_MAX_TRACKED_THREADS = 100
_DEFAULT_TOOL_FREQ_WARN = 30
_DEFAULT_TOOL_FREQ_HARD_LIMIT = 50
_MAX_PENDING_WARNINGS_PER_RUN = 4

_WARNING_MSG = (
    "[LOOP DETECTED] You are repeating the same tool calls. "
    "Stop calling tools and produce your final answer now."
)

_TOOL_FREQ_WARNING_MSG = (
    "[LOOP DETECTED] You have called {tool_name} {count} times "
    "without producing a final answer. Stop calling tools now."
)

_HARD_STOP_MSG = (
    "[FORCED STOP] Repeated tool calls exceeded the safety limit. "
    "Producing final answer with results collected so far."
)

_TOOL_FREQ_HARD_STOP_MSG = (
    "[FORCED STOP] Tool {tool_name} called {count} times — exceeded the per-tool safety limit."
)


def _normalize_tool_call_args(raw_args: object) -> tuple[dict[str, Any], str | None]:
    if isinstance(raw_args, dict):
        return raw_args, None
    if isinstance(raw_args, str):
        try:
            parsed = json.loads(raw_args)
        except (TypeError, ValueError, json.JSONDecodeError):
            return {}, raw_args
        if isinstance(parsed, dict):
            return parsed, None
        return {}, json.dumps(parsed, sort_keys=True, default=str)
    if raw_args is None:
        return {}, None
    return {}, json.dumps(raw_args, sort_keys=True, default=str)


def _stable_tool_key(name: str, args: dict[str, Any], fallback_key: str | None) -> str:
    if name == "read_file" and fallback_key is None:
        path = args.get("path") or ""
        try:
            start_line = int(args.get("start_line") or 1)
        except (TypeError, ValueError):
            start_line = 1
        try:
            end_line = int(args.get("end_line") or start_line)
        except (TypeError, ValueError):
            end_line = start_line
        start_line, end_line = sorted((start_line, end_line))
        bucket_size = 200
        return f"{path}:{(max(start_line, 1) - 1) // bucket_size}-{(max(end_line, 1) - 1) // bucket_size}"
    if name in {"write_file", "str_replace"}:
        if fallback_key is not None:
            return fallback_key
        return json.dumps(args, sort_keys=True, default=str)
    salient_fields = ("path", "url", "query", "command", "pattern", "glob", "cmd")
    stable_args = {f: args[f] for f in salient_fields if args.get(f) is not None}
    if stable_args:
        return json.dumps(stable_args, sort_keys=True, default=str)
    if fallback_key is not None:
        return fallback_key
    return json.dumps(args, sort_keys=True, default=str)


def _hash_tool_calls(tool_calls: list[dict[str, Any]]) -> str:
    normalized: list[str] = []
    for tc in tool_calls:
        name = tc.get("name", "")
        args, fallback_key = _normalize_tool_call_args(tc.get("args", {}))
        key = _stable_tool_key(name, args, fallback_key)
        normalized.append(f"{name}:{key}")
    normalized.sort()
    return hashlib.md5(json.dumps(normalized, sort_keys=True, default=str).encode()).hexdigest()[
        :12
    ]


class LoopDetectionMiddleware(AgentMiddleware):
    """Detects and breaks repetitive tool call loops."""

    def __init__(
        self,
        warn_threshold: int = _DEFAULT_WARN_THRESHOLD,
        hard_limit: int = _DEFAULT_HARD_LIMIT,
        window_size: int = _DEFAULT_WINDOW_SIZE,
        max_tracked_threads: int = _DEFAULT_MAX_TRACKED_THREADS,
        tool_freq_warn: int = _DEFAULT_TOOL_FREQ_WARN,
        tool_freq_hard_limit: int = _DEFAULT_TOOL_FREQ_HARD_LIMIT,
    ):
        super().__init__()
        self.warn_threshold = warn_threshold
        self.hard_limit = hard_limit
        self.window_size = window_size
        self.max_tracked_threads = max_tracked_threads
        self.tool_freq_warn = tool_freq_warn
        self.tool_freq_hard_limit = tool_freq_hard_limit
        self._lock = threading.Lock()
        self._history: OrderedDict[str, list[str]] = OrderedDict()
        self._warned: dict[str, set[str]] = defaultdict(set)
        self._tool_freq: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        self._tool_freq_warned: dict[str, set[str]] = defaultdict(set)
        self._pending_warnings: dict[tuple[str, str], list[str]] = defaultdict(list)
        self._pending_warning_touch_order: OrderedDict[tuple[str, str], None] = OrderedDict()
        self._max_pending_warning_keys = max(1, max_tracked_threads * 2)

    def _get_thread_id(self, runtime: Runtime) -> str:
        return "default"

    def _get_run_id(self, runtime: Runtime) -> str:
        return "default"

    def _pending_key(self, runtime: Runtime) -> tuple[str, str]:
        return self._get_thread_id(runtime), self._get_run_id(runtime)

    def _evict_if_needed(self) -> None:
        with self._lock:
            while len(self._history) > self.max_tracked_threads:
                evicted_id, _ = self._history.popitem(last=False)
                self._warned.pop(evicted_id, None)
                self._tool_freq.pop(evicted_id, None)
                self._tool_freq_warned.pop(evicted_id, None)
                for key in list(self._pending_warnings):
                    if key[0] == evicted_id:
                        self._drop_pending_warning_key_locked(key)

    def _drop_pending_warning_key_locked(self, key: tuple[str, str]) -> None:
        self._pending_warnings.pop(key, None)
        self._pending_warning_touch_order.pop(key, None)

    def _touch_pending_warning_key_locked(self, key: tuple[str, str]) -> None:
        self._pending_warning_touch_order[key] = None
        self._pending_warning_touch_order.move_to_end(key)

    def _prune_pending_warning_state_locked(self, protected_key: tuple[str, str]) -> None:
        overflow = len(self._pending_warning_touch_order) - self._max_pending_warning_keys
        if overflow <= 0:
            return
        candidates = [k for k in self._pending_warning_touch_order if k != protected_key]
        for key in candidates[:overflow]:
            self._drop_pending_warning_key_locked(key)

    def _queue_pending_warning(self, runtime: Runtime, warning: str) -> None:
        pending_key = self._pending_key(runtime)
        with self._lock:
            warnings = self._pending_warnings[pending_key]
            if warning not in warnings:
                warnings.append(warning)
            if len(warnings) > _MAX_PENDING_WARNINGS_PER_RUN:
                del warnings[: len(warnings) - _MAX_PENDING_WARNINGS_PER_RUN]
            self._touch_pending_warning_key_locked(pending_key)
            self._prune_pending_warning_state_locked(protected_key=pending_key)

    def _drain_pending_warnings(self, runtime: Runtime) -> list[str]:
        pending_key = self._pending_key(runtime)
        with self._lock:
            warnings = self._pending_warnings.pop(pending_key, [])
            self._pending_warning_touch_order.pop(pending_key, None)
        return warnings

    def _clear_other_run_pending_warnings(self, runtime: Runtime) -> None:
        thread_id, current_run_id = self._pending_key(runtime)
        with self._lock:
            for key in list(self._pending_warnings):
                if key[0] == thread_id and key[1] != current_run_id:
                    self._drop_pending_warning_key_locked(key)

    def _clear_current_run_pending_warnings(self, runtime: Runtime) -> None:
        pending_key = self._pending_key(runtime)
        with self._lock:
            self._drop_pending_warning_key_locked(pending_key)

    def _track_and_check(self, state: dict[str, Any], runtime: Runtime) -> tuple[str | None, bool]:
        messages = state.get("messages", [])
        if not messages:
            return None, False
        last_msg = messages[-1]
        if getattr(last_msg, "type", None) != "ai":
            return None, False
        tool_calls = getattr(last_msg, "tool_calls", None)
        if not tool_calls:
            return None, False

        thread_id = self._get_thread_id(runtime)
        call_hash = _hash_tool_calls(tool_calls)

        with self._lock:
            if thread_id in self._history:
                self._history.move_to_end(thread_id)
            else:
                self._history[thread_id] = []
                self._evict_if_needed()

            history = self._history[thread_id]
            history.append(call_hash)
            if len(history) > self.window_size:
                history[:] = history[-self.window_size :]

            warned_hashes = self._warned.get(thread_id)
            if warned_hashes is not None:
                warned_hashes.intersection_update(history)
                if not warned_hashes:
                    self._warned.pop(thread_id, None)

            count = history.count(call_hash)

            if count >= self.hard_limit:
                return _HARD_STOP_MSG, True
            if count >= self.warn_threshold:
                warned = self._warned[thread_id]
                if call_hash not in warned:
                    warned.add(call_hash)
                    return _WARNING_MSG, False

            freq = self._tool_freq[thread_id]
            for tc in tool_calls:
                name = tc.get("name", "")
                if not name:
                    continue
                freq[name] += 1
                tc_count = freq[name]
                if tc_count >= self.tool_freq_hard_limit:
                    return _TOOL_FREQ_HARD_STOP_MSG.format(tool_name=name, count=tc_count), True
                if tc_count >= self.tool_freq_warn:
                    warned = self._tool_freq_warned[thread_id]
                    if name not in warned:
                        warned.add(name)
                        return _TOOL_FREQ_WARNING_MSG.format(tool_name=name, count=tc_count), False
        return None, False

    @staticmethod
    def _append_text(content: str | list[Any] | None, text: str) -> str | list[Any]:
        if content is None:
            return text
        if isinstance(content, list):
            return [*content, {"type": "text", "text": f"\n\n{text}"}]
        return content + f"\n\n{text}"

    @staticmethod
    def _build_hard_stop_update(last_msg: Any, content: str | list[Any]) -> dict[str, Any]:
        update: dict[str, Any] = {"tool_calls": [], "content": content}
        additional_kwargs = dict(getattr(last_msg, "additional_kwargs", {}) or {})
        for key in ("tool_calls", "function_call"):
            additional_kwargs.pop(key, None)
        update["additional_kwargs"] = additional_kwargs
        response_metadata = deepcopy(getattr(last_msg, "response_metadata", {}) or {})
        if response_metadata.get("finish_reason") == "tool_calls":
            response_metadata["finish_reason"] = "stop"
        update["response_metadata"] = response_metadata
        return update

    def _apply(self, state: dict[str, Any], runtime: Runtime) -> dict[str, Any] | None:
        warning, hard_stop = self._track_and_check(state, runtime)
        if hard_stop:
            messages = state.get("messages", [])
            last_msg = messages[-1]
            content = self._append_text(last_msg.content, warning or _HARD_STOP_MSG)
            stripped_msg = last_msg.model_copy(
                update=self._build_hard_stop_update(last_msg, content)
            )
            return {"messages": [stripped_msg]}
        if warning:
            self._queue_pending_warning(runtime, warning)
            return None
        return None

    async def abefore_model(self, state: dict[str, Any], runtime: Runtime) -> dict[str, Any] | None:  # type: ignore[override]
        self._runtime = runtime
        self._clear_other_run_pending_warnings(runtime)
        return None

    async def aafter_model(self, state: dict[str, Any], runtime: Runtime) -> dict[str, Any] | None:  # type: ignore[override]
        self._runtime = runtime
        return self._apply(state, runtime)

    @staticmethod
    def _format_warning_message(warnings: list[str]) -> str:
        return "\n\n".join(dict.fromkeys(warnings))

    def _augment_request(self, request: Any) -> Any:
        runtime = getattr(self, "_runtime", None)
        if runtime is None:
            return request
        warnings = self._drain_pending_warnings(runtime)
        if not warnings:
            return request
        msg = self._format_warning_message(warnings)
        new_messages = [*request.messages, HumanMessage(content=msg, name="loop_warning")]
        return request.override(messages=new_messages)

    def wrap_model_call(self, request: Any, handler: Callable[[Any], Any]) -> Any:
        return handler(self._augment_request(request))

    async def awrap_model_call(self, request: Any, handler: Callable[[Any], Awaitable[Any]]) -> Any:
        return await handler(self._augment_request(request))

    def reset(self, thread_id: str | None = None) -> None:
        with self._lock:
            if thread_id:
                self._history.pop(thread_id, None)
                self._warned.pop(thread_id, None)
                self._tool_freq.pop(thread_id, None)
                self._tool_freq_warned.pop(thread_id, None)
                for key in list(self._pending_warnings):
                    if key[0] == thread_id:
                        self._drop_pending_warning_key_locked(key)
            else:
                self._history.clear()
                self._warned.clear()
                self._tool_freq.clear()
                self._tool_freq_warned.clear()
                self._pending_warnings.clear()
                self._pending_warning_touch_order.clear()
