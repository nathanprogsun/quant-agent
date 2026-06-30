# Skill + MCP + Subagent + Memory Parity — Implementation Plan (P0–P4)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring quant-agent to feature parity with deer-flow across four subsystems — Skill progressive disclosure, MCP server registration/scheduling, multi-subagent isolation, and memory evolution with prefix-cache-friendly frozen snapshots — by porting deer-flow's reference designs under the constraint of zero behavior regression in the existing 227-test baseline.

**Architecture:** Layered migration. **P0** establishes foundation (middleware ABC upgrade, ID-stable system message, .gitignore). **P1**–**P4** port deer-flow's reference modules on top of P0, each independently mergeable. Every port uses the same triple: `extensions_config.json` (config schema) + Python module (logic) + LangChain `AgentMiddleware` (integration point). Prefix-cache reuse is treated as a first-class invariant from P0.2 onward.

**Tech Stack:** Python 3.11+, langgraph 1.2.1, langchain-core 1.4.0, langchain-openai 1.2.2, pydantic v2, pytest, ruff, mypy. New deps (per plan): `langchain-mcp-adapters` (P2), optional `langchain-anthropic` (P4.1).

---

## 1. Background

### 1.1 Source audit

A third-party code audit (issued pre-2026-06-30, source: external review) identified five architectural patterns attributed to deer-flow that quant-agent lacks. Cross-verification (deer-flow HEAD `b3c312b7`) confirmed these are real reference implementations, not aspirational designs.

> **Path convention for deer-flow references:** Backend Python modules live under `backend/packages/harness/deerflow/` (cited as such throughout). The deer-flow frontend lives at the repo root (`frontend/...`), and deer-flow's own gateway routers live under `backend/app/gateway/...` (NOT under the harness package). These root paths are cited verbatim where they apply.

| Audit ID | Pattern | deer-flow reference |
|---|---|---|
| #2 | DeferredToolFilter + tool_search | `agents/middlewares/deferred_tool_filter_middleware.py` + `tools/builtins/tool_search.py` |
| #3 | Sub-agent isolation + token attribution | `subagents/executor.py` (persistent loop, checkpointer=False) + `token_usage_middleware.py` (tool_call_id bridge) |
| #4 | Memory frozen-snapshot | `agents/middlewares/dynamic_context_middleware.py` (ID-swap injection) + `claude_provider.py` (cache_control) |
| #5 | Skill progressive disclosure | `skills/` (SKILL.md protocol) + `agents/middlewares/skill_activation_middleware.py` (slash injection) |
| #6 | DanglingToolCallMiddleware | `agents/middlewares/dangling_tool_call_middleware.py` |

### 1.2 Quant-agent's stated next-quarter objectives

Quant-agent must implement: skill integration + MCP service registration/scheduling + multi-subagent capability + memory evolution. These objectives map 1:1 to P1–P4 below.

### 1.3 Problems this plan solves (cross-reference to review issue list)

| Problem ID | Severity | Plan that solves it |
|---|---|---|
| B1: `AgentMiddleware` ABC lacks `wrap_model_call`/`wrap_tool_call` | BLOCKER | **P0.1** |
| B2: System message rebuilt every turn; memory HumanMessage has no stable id; timestamp appended to system[0] | BLOCKER | **P0.2** (full frozen-snapshot ID-swap for date + agent_node persistence) + **P4.2** (memory extension) + **P4.3** + **P4.4** |
| B3: `TaskTool` is stub; `SubagentLimitMiddleware` is name-substring counter with no real traffic | BLOCKER | **P3.2** (TaskTool rewrite) + **P3.6** (limit middleware wired to real cache) |
| H1: No MCP server registry; `tools/mcp/client.py` is httpx stub | HIGH | **P2.1**–**P2.2** |
| H2: `SkillRegistry` orphan module; never referenced by agent | HIGH | **P1.1**–**P1.7** |
| H3: `SummarizationMiddleware` flag-only; no LLM call; no memory write-back | HIGH | **P4.5** |
| H4: No `DanglingToolCallMiddleware`; tool_call_id dangling will 400 OpenAI-compatible reasoning models | HIGH | **P2.4** |
| M1: No `extensions_config.json` / `mcpServers` config | MEDIUM | **P1.5** (skill) + **P2.2** (MCP) |
| M2: `checkpoints.db-shm` / `-wal` untracked | MEDIUM | **P0.3** |
| M3: `MemoryMiddleware` runs after `DynamicContextMiddleware`; ordering undocumented | MEDIUM | **P4.4** (id-swap makes order irrelevant) |
| M4: `ToolNode` errors leave tool_call_id dangling; subagent-unsafe | MEDIUM | **P2.4** |
| M5: `SkillDefinition.prompt_template` inline body — opposite of progressive-disclosure | MEDIUM | **P1.7** (migration script) |
| M6: Frontend `InputBox.tsx` lacks slash-command UI | MEDIUM | **P1.6** |
| M7: No `read_file` tool | MEDIUM | **P1.4** |
| L1: `MemoryService.to_prompt_string()` no token budget | LOW | **P4.4** (token budget enforcement) |
| L2: `UserMemory.confidence` field unused | LOW | **P4.6** (threshold gating) |
| L3: `MemoryFact.embedding` field exists but no index | LOW | **P4.6** (drop or index decision) |
| L4: `test_lead_agent.py` coverage thin for middleware chain | LOW | Each plan adds its own regression tests |
| L5: Manual `StateGraph` vs `create_agent` | LOW | **P0.1** enables gradual migration; final decision deferred |

### 1.4 Constraints

- Zero behavior regression: existing 227 tests must remain green after every commit.
- Prefix-cache stability must not degrade: any change to prompt assembly must be proven stable via new test (no implicit id drift).
- No code change in P0 PR may import or depend on P1–P4 modules (forward dependency forbidden).
- Each P1–P4 subplan must merge independently (no "everything together" PR).

---

## 2. Decisions log

- **D1**: KEEP the custom `AgentMiddleware` ABC; do NOT migrate to `langchain.agents.middleware.AgentMiddleware`. Reason: the `langchain` package is not installed in quant-agent (only `langchain-core`/`langgraph`/`langchain-openai`), and langchain's ABC uses `(state, runtime: Runtime)` signatures — migrating would force a signature rewrite of all 8 existing middlewares and violate the zero-regression constraint. Instead, P0.1 extends the custom ABC with the full `wrap_*` hook surface (`wrap_model_call`/`awrap_model_call`/`wrap_tool_call`/`awrap_tool_call`) needed by P1–P4. deer-flow's `before_agent`/`after_agent` hooks have NO equivalent in quant-agent's hand-rolled `agent_node` (manual `StateGraph`, not `create_agent`); their injection points map to `before_model`/`after_model` inside `agent_node`. Ports therefore ADAPT to `before_model`/`after_model`/`wrap_*` rather than copy deer-flow's `before_agent` verbatim. This is an explicit adaptation, noted per-task.
- **D2**: Prefix-cache strategy treats the **first user HumanMessage's id as the id-swap anchor** (deer-flow `dynamic_context_middleware.py:206` convention). On the first turn, that HumanMessage is replaced in-place (same id) by a `SystemMessage` carrying the date; an optional `HumanMessage(id="{stable_id}__memory")` carries memory; the original user text becomes `HumanMessage(id="{stable_id}__user")`. The first-turn block is then FROZEN — content never changes again — so prefix cache hits on every subsequent turn. Date granularity is DAY (`%Y-%m-%d, %A`), not second. A lightweight date-update reminder is injected only on midnight crossing (at the current/last HumanMessage, also via id-swap). Framework-owned data (date) uses `SystemMessage`; user-owned data (memory) stays `HumanMessage` (OWASP LLM01 role separation).
- **D9**: `agent_node` MUST persist middleware message patches. Today it returns `{"messages": [response], ...state_patches}` (lead_agent.py:148), so `before_model` injections are ephemeral and `add_messages` never sees them — making D2's "replace in place across turns" impossible. P0.2 changes `agent_node` to return `{"messages": <patched messages> + [response], ...state_patches}`. Because `add_messages` dedups/replaces by id, returning the full patched list is idempotent for unchanged messages and persists new injected messages. This is a behavior-equivalent change guarded by a regression test.
- **D3**: Configuration split follows deer-flow: `extensions_config.json` for runtime-toggleable state (skills, MCP servers, interceptors); `backend/app/settings.py` (pydantic-settings) for boot-time config (model, paths, debounce). Both load via the same `ExtensionsConfig.from_file()` pattern.
- **D4**: File-based memory storage (deer-flow convention) is NOT adopted. quant-agent retains Postgres `UserMemory`/`MemoryFact` schema. Evolution pipeline (updater/queue/hook) is ported to write to Postgres tables.
- **D5**: `checkpointer=False` is enforced for subagents at compile time (hardcoded in `SubagentExecutor`, not configurable). Regression test guards against accidental parent-checkpointer inheritance.
- **D6**: `langchain-mcp-adapters` is the only MCP client library used. No hand-rolled JSON-RPC.
- **D7**: All new tests must follow AAA pattern (per CLAUDE.md testing rule). Tests live under `backend/tests/unit/` or `backend/tests/integration/` mirroring the source tree.
- **D8**: Commit messages follow conventional commits (per CLAUDE.md git-workflow rule).

---

## 3. Dependency graph

```
                    ┌─ P1 (Skill) ─────────────────────────┐
                    │                                       │
P0 (Foundation) ────┼─ P2.1 (langchain-mcp-adapters)        │
                    │      └─ P2.2 (MCP session pool)       │
                    │      └─ P2.3 (DeferredToolFilter +    │
                    │            tool_search)               │
                    │      └─ P2.4 (DanglingToolCall) ──────┼──┐
                    │                                       │  │
                    │                                       │  v
                    │                                       │ P3 (Subagent) needs P2.4
                    │                                       │
                    └─ P4 (Memory evolution) ───────────────┘
                       (independent of P1/P2/P3 except P0)
```

Critical paths:
- **P0 → P1, P2, P4**: foundation gates all ports.
- **P2.4 → P3.2**: DanglingToolCall middleware must exist before TaskTool rewrite can use it safely.
- **P1 / P2 / P3 / P4 → P5 (out of scope)**: deprecation, docs, perf baseline.

---

# Plan-0: Foundation

**Scope:** Unblock P1–P4 by adding the `wrap_*` hook surface to `AgentMiddleware`; stabilize system-message id so future prefix-cache work has a stable anchor; fix `.gitignore` for SQLite WAL files.

**Solves:** B1 (BLOCKER), B2 (full frozen-snapshot ID-swap for the date portion; memory ID-swap deepened in P4.4), M2 (MEDIUM).

**Exit criteria:**
- Existing 227 tests still pass.
- New test `test_middleware_abc_wrap_model_call.py` passes (6 cases, incl. `wrap_tool_call`).
- New test `test_dynamic_context_id_stable.py` passes (4 cases: first-turn id-swap, same-day frozen, no system mutation, midnight crossing).
- `git status` no longer lists `checkpoints.db-shm` or `checkpoints.db-wal`.

**Files touched:**
- `backend/app/core/chat/middlewares/base.py` (modify)
- `backend/app/core/chat/agent/lead_agent.py` (modify — remove double `_ensure_system_message` call)
- `backend/app/core/chat/middlewares/dynamic_context_middleware.py` (modify — ID-swap injection)
- `backend/tests/unit/chat/middlewares/test_middleware_abc_wrap_model_call.py` (create)
- `backend/tests/unit/chat/middlewares/test_dynamic_context_id_stable.py` (create)
- `.gitignore` (modify)
- `checkpoints.db-shm`, `checkpoints.db-wal` (untrack)

---

## Task 0.1: Add `wrap_model_call` / `wrap_tool_call` hook surface to AgentMiddleware

**Files:**
- Modify: `backend/app/core/chat/middlewares/base.py:9-32`
- Test: `backend/tests/unit/chat/middlewares/test_middleware_abc_wrap_model_call.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/unit/chat/middlewares/test_middleware_abc_wrap_model_call.py`:

```python
"""Tests for AgentMiddleware wrap_* hook surface.

The ABC must expose wrap_model_call/awrap_model_call (model interceptors)
and wrap_tool_call/awrap_tool_call (tool interceptors). All four default
to no-ops that delegate to the wrapped handler. Subclasses may override
to intercept model or tool calls.
"""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.core.chat.middlewares.base import AgentMiddleware


class _IdentityMW(AgentMiddleware):
    """Minimal subclass that does not override any hook."""


@pytest.mark.asyncio
async def test_default_awrap_model_call_invokes_handler_unchanged() -> None:
    mw = _IdentityMW()
    seen: dict[str, Any] = {}

    async def handler(request: Any) -> Any:
        seen["called"] = True
        return "ok"

    result = await mw.awrap_model_call(request=None, handler=handler)
    assert result == "ok"
    assert seen["called"] is True


@pytest.mark.asyncio
async def test_awrap_model_call_can_short_circuit() -> None:
    class ShortCircuitMW(AgentMiddleware):
        async def awrap_model_call(self, request: Any, handler: Any) -> Any:
            return "short-circuited"

    mw = ShortCircuitMW()
    handler = AsyncMock(return_value="original")
    result = await mw.awrap_model_call(request=None, handler=handler)
    assert result == "short-circuited"
    handler.assert_not_awaited()


def test_wrap_model_call_sync_default_exists_and_is_noop() -> None:
    mw = _IdentityMW()
    called = {"v": False}

    def handler(request: Any) -> Any:
        called["v"] = True
        return "sync-ok"

    # Sync hook must exist and delegate by default
    result = mw.wrap_model_call(request=None, handler=handler)
    assert result == "sync-ok"
    assert called["v"] is True


@pytest.mark.asyncio
async def test_awrap_model_call_subclass_override() -> None:
    class TransformMW(AgentMiddleware):
        async def awrap_model_call(self, request: Any, handler: Any) -> Any:
            out = await handler(request)
            return f"<wrapped>{out}</wrapped>"

    mw = TransformMW()

    async def handler(request: Any) -> Any:
        return "body"

    result = await mw.awrap_model_call(request=None, handler=handler)
    assert result == "<wrapped>body</wrapped>"


@pytest.mark.asyncio
async def test_default_awrap_tool_call_invokes_handler_unchanged() -> None:
    mw = _IdentityMW()
    seen: dict[str, Any] = {}

    async def handler(request: Any) -> Any:
        seen["called"] = True
        return "tool-ok"

    result = await mw.awrap_tool_call(request=None, handler=handler)
    assert result == "tool-ok"
    assert seen["called"] is True


def test_wrap_tool_call_sync_default_exists_and_is_noop() -> None:
    mw = _IdentityMW()
    called = {"v": False}

    def handler(request: Any) -> Any:
        called["v"] = True
        return "sync-tool-ok"

    result = mw.wrap_tool_call(request=None, handler=handler)
    assert result == "sync-tool-ok"
    assert called["v"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/jung/pro/quant-agent/backend && uv run pytest tests/unit/chat/middlewares/test_middleware_abc_wrap_model_call.py -v`
Expected: FAIL with `AttributeError: 'AgentMiddleware' object has no attribute 'awrap_model_call'`.

- [ ] **Step 3: Modify `base.py`**

Replace `backend/app/core/chat/middlewares/base.py` content with:

```python
"""Agent middleware base class."""

from __future__ import annotations

from abc import ABC
from typing import Any, Awaitable, Callable


class AgentMiddleware(ABC):
    """Agent middleware with four legacy hooks plus two wrap_* interceptors.

    Legacy hooks (before_/after_model/tool) remain unchanged for backward
    compatibility with the existing 8 middlewares. New code should prefer
    wrap_model_call / wrap_tool_call which give full control over the
    call site and can short-circuit, transform, or retry.
    """

    # ----- Legacy hooks (existing) -----

    async def before_model(self, state: dict[str, Any], config: dict[str, Any]) -> dict[str, Any] | None:
        """Before LLM call. Return modified state or None."""
        return None

    async def after_model(self, state: dict[str, Any], config: dict[str, Any]) -> dict[str, Any] | None:
        """After LLM call. Return modified state or None."""
        return None

    async def before_tool(self, tool_name: str, tool_input: dict[str, Any], config: dict[str, Any]) -> dict[str, Any] | None:
        """Before tool call. Return modified tool_input or None."""
        return None

    async def after_tool(
        self, tool_name: str, tool_input: dict[str, Any], result: Any, config: dict[str, Any]
    ) -> Any | None:
        """After tool call. Return modified result or None."""
        return None

    # ----- Wrap interceptors (new) -----

    async def awrap_model_call(
        self,
        request: Any,
        handler: Callable[[Any], Awaitable[Any]],
    ) -> Any:
        """Async wrap around the model call. Default delegates to handler.

        Subclasses override to inspect/modify `request`, call `handler`,
        and transform the result. Returning without calling handler
        short-circuits the model call.
        """
        return await handler(request)

    def wrap_model_call(
        self,
        request: Any,
        handler: Callable[[Any], Any],
    ) -> Any:
        """Sync wrap around the model call. Default delegates to handler."""
        return handler(request)

    async def awrap_tool_call(
        self,
        request: Any,
        handler: Callable[[Any], Awaitable[Any]],
    ) -> Any:
        """Async wrap around a tool call. Default delegates to handler.

        Required by P2.3 DeferredToolFilter (deer-flow overrides
        `awrap_tool_call` to gate/redirect deferred tool calls). Returning
        without calling handler short-circuits the tool call.
        """
        return await handler(request)

    def wrap_tool_call(
        self,
        request: Any,
        handler: Callable[[Any], Any],
    ) -> Any:
        """Sync wrap around a tool call. Default delegates to handler."""
        return handler(request)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/jung/pro/quant-agent/backend && uv run pytest tests/unit/chat/middlewares/test_middleware_abc_wrap_model_call.py -v`
Expected: 6 passed.

- [ ] **Step 5: Run full suite to verify no regression**

Run: `cd /Users/jung/pro/quant-agent/backend && make test`
Expected: 227 + 6 = 233 passed, 0 failed.

- [ ] **Step 6: Commit**

```bash
cd /Users/jung/pro/quant-agent
git add backend/app/core/chat/middlewares/base.py \
        backend/tests/unit/chat/middlewares/test_middleware_abc_wrap_model_call.py
git commit -m "feat(middleware): add wrap_model_call/wrap_tool_call hooks

Adds wrap interceptors to the custom AgentMiddleware ABC:
wrap_model_call/awrap_model_call and wrap_tool_call/awrap_tool_call.
Default implementations are no-op delegates so the existing 8 middlewares
are unaffected. wrap_model_call backs P1 SkillActivation, P2 DanglingToolCall,
P2 DeferredToolFilter; wrap_tool_call backs P2 DeferredToolFilter's tool
gate. Does NOT migrate to langchain's AgentMiddleware ABC (keeps the
(state, config: dict) signature) to avoid rewriting all 8 middlewares."
```

---

## Task 0.2: ID-stable system message + ID-swap dynamic context injection

**Files:**
- Modify: `backend/app/core/chat/agent/lead_agent.py:42-55, 127, 142`
- Modify: `backend/app/core/chat/middlewares/dynamic_context_middleware.py:13-39`
- Test: `backend/tests/unit/chat/middlewares/test_dynamic_context_id_stable.py`

**Why:** Two root causes break prefix-cache reuse on every turn. (1) `_ensure_system_message` constructs a fresh `SystemMessage` on every `agent_node` call and is called **twice** per turn (lead_agent.py:127 and :142); each call yields a new instance with a different default id. (2) `DynamicContextMiddleware.before_model` mutates `messages[0].content` to append a **second-granularity** UTC timestamp (`%Y-%m-%d %H:%M:%S`) — the content changes every second, so the prefix from `messages[0]` onward is never cache-stable. Fix ports deer-flow's `dynamic_context_middleware.py:125-307` frozen-snapshot pattern, ADAPTED to quant-agent's `before_model` hook (quant-agent uses a manual `StateGraph`/`agent_node`, not langchain `create_agent`, so deer-flow's `before_agent` maps to `before_model`): (a) the **first user HumanMessage's id** is the id-swap anchor (D2); (b) date granularity is **day** (`%Y-%m-%d, %A`); (c) the first-turn reminder is **frozen** — content never changes on same-day subsequent turns; (d) midnight crossing injects a date-update reminder at the **last** HumanMessage; (e) framework data (date) uses `SystemMessage`; (f) `agent_node` MUST persist the middleware's patched messages (D9) — today it returns `{"messages": [response]}`, so the id-swap is ephemeral.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/unit/chat/middlewares/test_dynamic_context_id_stable.py`:

```python
"""DynamicContextMiddleware — frozen-snapshot ID-swap (deer-flow port).

First turn: the first user HumanMessage is replaced in-place (same id) by
a SystemMessage <system-reminder> carrying the current date; the original
user text is re-emitted as HumanMessage(id="{stable_id}__user"). The
injected block is FROZEN — content never changes on subsequent same-day
turns, so prefix cache hits every turn. Midnight crossing injects a
date-update reminder before the current (last) HumanMessage.
"""
from __future__ import annotations

from typing import Any

import pytest
from langchain_core.messages import HumanMessage, SystemMessage

from app.core.chat.middlewares.dynamic_context_middleware import (
    DynamicContextMiddleware,
    _REMINDER_DATE_KEY,
    _REMINDER_KWARG,
)


def _reminder(content: str, msg_id: str, date: str) -> SystemMessage:
    return SystemMessage(
        content=content,
        id=msg_id,
        additional_kwargs={
            _REMINDER_KWARG: True,
            _REMINDER_DATE_KEY: date,
            "hide_from_ui": True,
        },
    )


@pytest.mark.asyncio
async def test_first_turn_swaps_first_human_message_into_system_reminder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.core.chat.middlewares.dynamic_context_middleware._current_date",
        lambda: "2026-06-30, Monday",
    )
    mw = DynamicContextMiddleware()
    state: dict[str, Any] = {
        "messages": [SystemMessage(content="sys"), HumanMessage(content="hello", id="u1")]
    }
    out = await mw.before_model(state, {})
    assert out is not None
    msgs = out["messages"]
    # Original HumanMessage id="u1" is replaced by a SystemMessage reminder with the SAME id
    reminder = [m for m in msgs if isinstance(m, SystemMessage) and m.id == "u1"]
    assert len(reminder) == 1, f"expected one reminder SystemMessage id=u1, got ids={[m.id for m in msgs]}"
    assert "<current_date>2026-06-30, Monday</current_date>" in reminder[0].content
    # Original user text preserved as HumanMessage(id="u1__user")
    user_msg = [m for m in msgs if isinstance(m, HumanMessage) and m.id == "u1__user"]
    assert len(user_msg) == 1 and user_msg[0].content == "hello"
    # No leftover HumanMessage with the original id (it was swapped away)
    assert not any(isinstance(m, HumanMessage) and m.id == "u1" for m in msgs)


@pytest.mark.asyncio
async def test_same_day_subsequent_turn_is_frozen(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.core.chat.middlewares.dynamic_context_middleware._current_date",
        lambda: "2026-06-30, Monday",
    )
    mw = DynamicContextMiddleware()
    # State AFTER first turn (persisted): reminder + __user already present, plus a 2nd user msg
    state: dict[str, Any] = {
        "messages": [
            SystemMessage(content="sys"),
            _reminder(
                "<system-reminder>\n<current_date>2026-06-30, Monday</current_date>\n</system-reminder>",
                "u1",
                "2026-06-30, Monday",
            ),
            HumanMessage(content="hello", id="u1__user"),
            HumanMessage(content="second question", id="u2"),
        ]
    }
    out = await mw.before_model(state, {})
    # Frozen: same day → no patch
    assert out is None, "same-day subsequent turn must be frozen (no patch)"


@pytest.mark.asyncio
async def test_does_not_mutate_static_system_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.core.chat.middlewares.dynamic_context_middleware._current_date",
        lambda: "2026-06-30, Monday",
    )
    mw = DynamicContextMiddleware()
    sys_content = "static system prompt"
    state: dict[str, Any] = {
        "messages": [SystemMessage(content=sys_content), HumanMessage(content="hi", id="u1")]
    }
    out = await mw.before_model(state, {})
    msgs = out["messages"]
    # messages[0] static SystemMessage.content MUST be unchanged
    assert isinstance(msgs[0], SystemMessage)
    assert msgs[0].content == sys_content


@pytest.mark.asyncio
async def test_midnight_crossing_injects_date_update_at_last_human(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Persisted first-turn reminder is from yesterday; today is the next day
    monkeypatch.setattr(
        "app.core.chat.middlewares.dynamic_context_middleware._current_date",
        lambda: "2026-07-01, Tuesday",
    )
    mw = DynamicContextMiddleware()
    state: dict[str, Any] = {
        "messages": [
            SystemMessage(content="sys"),
            _reminder(
                "<system-reminder>\n<current_date>2026-06-30, Monday</current_date>\n</system-reminder>",
                "u1",
                "2026-06-30, Monday",
            ),
            HumanMessage(content="hello", id="u1__user"),
            HumanMessage(content="good morning", id="u2"),
        ]
    }
    out = await mw.before_model(state, {})
    assert out is not None
    msgs = out["messages"]
    # A NEW date-update SystemMessage reminder is injected with reminder_date=today
    updates = [
        m for m in msgs
        if isinstance(m, SystemMessage) and m.additional_kwargs.get(_REMINDER_DATE_KEY) == "2026-07-01, Tuesday"
    ]
    assert len(updates) == 1, f"expected one date-update reminder, got ids={[m.id for m in msgs]}"
    # It reuses the last HumanMessage id (u2) via id-swap
    assert updates[0].id == "u2"
    # Original last user text preserved as u2__user
    assert any(
        isinstance(m, HumanMessage) and m.id == "u2__user" and m.content == "good morning"
        for m in msgs
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/jung/pro/quant-agent/backend && uv run pytest tests/unit/chat/middlewares/test_dynamic_context_id_stable.py -v`
Expected: FAIL — current implementation mutates `messages[0].content` (test_does_not_mutate_static_system_message fails), and does not perform an id-swap (test_first_turn_swaps_first_human_message_into_system_reminder fails).

- [ ] **Step 3: Rewrite `DynamicContextMiddleware`**

Replace `backend/app/core/chat/middlewares/dynamic_context_middleware.py` with:

```python
"""Dynamic context injection middleware — frozen-snapshot ID-swap.

Ports deer-flow's dynamic_context_middleware.py:125-307 frozen-snapshot
pattern, ADAPTED to quant-agent's before_model hook (quant-agent uses a
manual StateGraph agent_node, not langchain create_agent, so deer-flow's
before_agent maps to before_model here).

First turn
----------
Finds the first user HumanMessage and replaces it IN-PLACE (same id) with
a SystemMessage <system-reminder> carrying the current date. The original
user text is re-emitted as HumanMessage(id="{stable_id}__user"). The
injected block is then FROZEN — its content never changes again, so the
prefix cache hits on every subsequent turn.

Midnight crossing
-----------------
If the current date differs from the last injected date, a lightweight
date-update SystemMessage is spliced in before the current (last)
HumanMessage (also via id-swap) and persisted. Subsequent turns on the
new day see the corrected date and skip re-injection.

Date granularity is DAY (%Y-%m-%d, %A), never second. Framework-owned
data (date) uses SystemMessage; memory (P4.4) will use HumanMessage with
id="{stable_id}__memory" (OWASP LLM01 role separation).
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Any

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from app.core.chat.middlewares.base import AgentMiddleware

_REMINDER_KWARG = "dynamic_context_reminder"
_REMINDER_DATE_KEY = "reminder_date"


def _current_date() -> str:
    """Current date at day granularity. Monkeypatched in tests."""
    return datetime.now().strftime("%Y-%m-%d, %A")


def _date_reminder(date_str: str) -> str:
    return "\n".join(
        ("<system-reminder>", f"<current_date>{date_str}</current_date>", "</system-reminder>")
    )


def _is_reminder(msg: object) -> bool:
    return isinstance(msg, (HumanMessage, SystemMessage)) and bool(
        msg.additional_kwargs.get(_REMINDER_KWARG)
    )


def _last_injected_date(messages: list[BaseMessage]) -> str | None:
    """Most recently injected date, read from additional_kwargs (not content)."""
    for m in reversed(messages):
        if not _is_reminder(m):
            continue
        d = m.additional_kwargs.get(_REMINDER_DATE_KEY)
        if isinstance(d, str) and d:
            return d
    return None


def _is_user_injection_target(msg: object) -> bool:
    if not isinstance(msg, HumanMessage):
        return False
    if _is_reminder(msg):
        return False
    # Prevent recursive ID-swap on already-rewritten __user messages
    # (would cause id__user__user... suffix growth and ghost re-execution).
    if msg.id and str(msg.id).endswith("__user"):
        return False
    return True


def _make_reminder_and_user(
    original: HumanMessage, reminder_content: str, *, reminder_date: str
) -> list[BaseMessage]:
    """ID-swap triple: SystemMessage takes the original id; user text -> {id}__user."""
    stable_id = original.id or str(uuid.uuid4())
    return [
        SystemMessage(
            content=reminder_content,
            id=stable_id,
            additional_kwargs={
                _REMINDER_KWARG: True,
                _REMINDER_DATE_KEY: reminder_date,
                "hide_from_ui": True,
            },
        ),
        HumanMessage(
            content=original.content,
            id=f"{stable_id}__user",
            name=original.name,
            additional_kwargs=original.additional_kwargs,
        ),
    ]


class DynamicContextMiddleware(AgentMiddleware):
    """Frozen-snapshot date injection via ID-swap (deer-flow port)."""

    async def before_model(
        self, state: dict[str, Any], config: dict[str, Any]
    ) -> dict[str, Any] | None:
        messages = list(state.get("messages", []))
        if not messages:
            return None

        current_date = _current_date()
        last_date = _last_injected_date(messages)

        if last_date is None:
            # First turn: inject full reminder at the first user HumanMessage
            first_idx = next(
                (i for i, m in enumerate(messages) if _is_user_injection_target(m)), None
            )
            if first_idx is None:
                return None
            triple = _make_reminder_and_user(
                messages[first_idx],
                _date_reminder(current_date),
                reminder_date=current_date,
            )
            new_messages = messages[:first_idx] + triple + messages[first_idx + 1 :]
            return {"messages": new_messages}

        if last_date == current_date:
            # Same day: frozen — nothing to do
            return None

        # Midnight crossed: inject date-update at the last user HumanMessage
        last_idx = next(
            (i for i in reversed(range(len(messages))) if _is_user_injection_target(messages[i])),
            None,
        )
        if last_idx is None:
            return None
        triple = _make_reminder_and_user(
            messages[last_idx],
            _date_reminder(current_date),
            reminder_date=current_date,
        )
        new_messages = messages[:last_idx] + triple + messages[last_idx + 1 :]
        return {"messages": new_messages}
```

- [ ] **Step 4: Persist middleware message patches in `agent_node` (D9) + remove duplicate `_ensure_system_message`**

In `backend/app/core/chat/agent/lead_agent.py`:

- Remove the redundant `_ensure_system_message` call at line 142 (the one after `before_model` hooks). The call at line 127 remains (entry-point normalization).
- **Change the return value** so the id-swapped messages persist. Today `agent_node` returns `{"messages": [response], ...state_patches}` (lead_agent.py:148), so `before_model`'s patched messages are ephemeral and `add_messages` never sees the id-swap. Return the full patched list plus the response instead. This is idempotent: `ThreadState.messages` uses the `add_messages` reducer, and langgraph assigns ids to all checkpointed messages, so returning the patched list replaces existing messages in-place by id and appends only genuinely new messages (the `{id}__user` message and the response).
- Fix `preview_state` accordingly so `after_model` hooks see the patched list + response (not a duplicated concatenation).

The relevant section (lines 130–159) becomes:

```python
        # before_model hooks — must see the system prompt so middlewares do not drop it
        state_patches: dict[str, Any] = {}
        for mw in middlewares:
            modified = await mw.before_model(working_state, {})
            if modified:
                for key, value in modified.items():
                    if key == "messages":
                        messages = value
                        working_state["messages"] = messages
                    else:
                        state_patches[key] = value

        # NOTE: do NOT call _ensure_system_message again here.
        # DynamicContextMiddleware performs an ID-swap (first HumanMessage ->
        # SystemMessage reminder + {id}__user). Re-running _ensure_system_message
        # would rebuild the SystemMessage and break the frozen-snapshot prefix
        # cache. System message identity is preserved from the entry-point call.

        # LLM call — `messages` is the full patched list (id-swap applied)
        response = await model.ainvoke(messages)

        # D9: persist the patched message list. Returning [*messages, response]
        # lets the add_messages reducer replace-in-place by id (the swapped
        # SystemMessage) and append the new {id}__user message + response.
        # Without this the ID-swap is ephemeral and prefix-cache reuse across
        # turns is impossible. Idempotent because add_messages assigns ids to
        # all checkpointed messages.
        state_update: dict[str, Any] = {"messages": [*messages, response], **state_patches}
        preview_state = {**working_state, "messages": [*messages, response]}
        for mw in middlewares:
            modified = await mw.after_model(preview_state, {})
            if modified:
                state_update.update(modified)

        return state_update
```

- [ ] **Step 5: Run new test to verify it passes**

Run: `cd /Users/jung/pro/quant-agent/backend && uv run pytest tests/unit/chat/middlewares/test_dynamic_context_id_stable.py -v`
Expected: 4 passed.

- [ ] **Step 6: Run full suite to verify no regression**

Run: `cd /Users/jung/pro/quant-agent/backend && make test`
Expected: 233 + 4 = 237 passed.

- [ ] **Step 7: Commit**

```bash
cd /Users/jung/pro/quant-agent
git add backend/app/core/chat/middlewares/dynamic_context_middleware.py \
        backend/app/core/chat/agent/lead_agent.py \
        backend/tests/unit/chat/middlewares/test_dynamic_context_id_stable.py
git commit -m "fix(middleware): frozen-snapshot ID-swap dynamic-context injection

Ports deer-flow's dynamic_context_middleware frozen-snapshot pattern:
- Anchors on the first user HumanMessage's id (D2), not a thread_id.
- Replaces that HumanMessage in-place with a SystemMessage <system-reminder>
  carrying the current DATE (day granularity); original user text becomes
  HumanMessage(id='{stable_id}__user'). Frozen after first turn.
- Midnight crossing injects a date-update reminder at the last HumanMessage.
- Framework data (date) in SystemMessage; memory (P4.2) will stay HumanMessage.

Replaces the prior 'append second-granularity timestamp to SystemMessage
content' approach, which changed the prefix every second and broke
Anthropic/OpenAI prefix-cache reuse on every turn.

Also (D9) makes agent_node persist before_model message patches by returning
[*messages, response] so add_messages replaces-in-place by id; previously
the injection was ephemeral. Removes the duplicate _ensure_system_message
call at lead_agent.py:142."
```

---

## Task 0.3: Fix .gitignore for SQLite WAL files

**Files:**
- Modify: `/Users/jung/pro/quant-agent/.gitignore:37-39`
- Untrack: `backend/checkpoints.db-shm`, `backend/checkpoints.db-wal`

**Why:** `AsyncSqliteSaver` (langgraph checkpointer) creates `checkpoints.db`, `checkpoints.db-wal`, `checkpoints.db-shm` in WAL mode. The `-wal` and `-shm` siblings are runtime state, not versioned data; existing `.gitignore` patterns (`*.db`, `*.sqlite`, `*.sqlite3`) miss them.

- [ ] **Step 1: Verify the issue**

Run:
```bash
cd /Users/jung/pro/quant-agent
git status --porcelain | grep -E '(checkpoints\.db|shm|wal)'
```
Expected output (or similar):
```
?? backend/checkpoints.db-shm
?? backend/checkpoints.db-wal
```

- [ ] **Step 2: Modify `.gitignore`**

Append to `.gitignore` (after line 39):

```
# SQLite WAL/SHM journal siblings (langgraph AsyncSqliteSaver)
*.db-shm
*.db-wal
```

- [ ] **Step 3: Verify .gitignore covers the files**

Run:
```bash
cd /Users/jung/pro/quant-agent
git check-ignore -v backend/checkpoints.db-shm backend/checkpoints.db-wal
```
Expected: each line prints a `.gitignore:<lineno>:<pattern>` line confirming match.

- [ ] **Step 4: No commit needed if files were never tracked**

Run:
```bash
cd /Users/jung/pro/quant-agent
git status --porcelain | grep -E '(checkpoints\.db|shm|wal)'
```
Expected: empty output.

- [ ] **Step 5: Commit (gitignore change only)**

```bash
cd /Users/jung/pro/quant-agent
git add .gitignore
git commit -m "chore(gitignore): exclude SQLite WAL/SHM journal files

AsyncSqliteSaver (langgraph checkpointer) creates .db-wal and .db-shm
siblings next to checkpoints.db. They are runtime journal state, not
versioned data, and were showing as untracked in git status."
```

---

# Plan-1: Skill Progressive Disclosure

**Scope:** Port deer-flow's skill system to quant-agent. Introduce SKILL.md disk protocol, metadata-only system-prompt section with LRU cache, `/<skill-name>` slash command injection via middleware, `read_file` tool, REST toggle API, frontend autocomplete UI, migration of legacy `SkillRegistry` data.

**Solves:** H2, M1 (skill portion), M5, M6, M7.

**Reference (deer-flow):**
- Disk protocol: `backend/packages/harness/deerflow/skills/{parser,types,slash,storage/}*.py`
- Prompt section: `backend/packages/harness/deerflow/agents/lead_agent/prompt.py:99-100, 364-580, 629-696`
- Slash middleware: `backend/packages/harness/deerflow/agents/middlewares/skill_activation_middleware.py:66-289`
- Config: `backend/packages/harness/deerflow/config/extensions_config.py:69-86, 211` + `backend/packages/harness/deerflow/config/skills_config.py:16-72`
- REST: `backend/app/gateway/routers/skills.py:88-352` (deer-flow root, not under the harness package)
- Frontend: `frontend/src/components/workspace/input-box.tsx:126-150, 481-563` (deer-flow root)

**Exit criteria:**
- SKILL.md YAML frontmatter parsing covered by unit tests.
- `_get_cached_skills_prompt_section` is byte-stable across identical inputs (LRU hit).
- Typing `/research` in chat triggers `SkillActivationMiddleware` injection (verified via integration test).
- `read_file` tool returns SKILL.md body when LLM requests it.
- PUT `/api/skills/{name}` toggles enabled state and invalidates LRU cache.
- Old `SkillDefinition.prompt_template` data migrates to `skills/custom/<name>/SKILL.md` files.

---

## Task 1.1: SKILL.md disk protocol

**Files:**
- Create: `backend/app/skills/__init__.py`
- Create: `backend/app/skills/parser.py`
- Create: `backend/app/skills/types.py`
- Create: `backend/app/skills/exceptions.py`
- Test: `backend/tests/unit/skills/test_parser.py`

**Step 1: Write failing tests**

Create `backend/tests/unit/skills/test_parser.py`:

```python
"""Tests for SKILL.md frontmatter parser."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.skills.exceptions import SkillParseError, SkillValidationError
from app.skills.parser import parse_skill_file
from app.skills.types import SkillCategory


def _write(tmp: Path, name: str, body: str) -> Path:
    p = tmp / "SKILL.md"
    p.write_text(body, encoding="utf-8")
    return p


def test_parse_minimal_frontmatter(tmp_path: Path) -> None:
    p = _write(tmp_path, "minimal", "---\nname: minimal\ndescription: short\n---\n# Body\n")
    skill = parse_skill_file(p, category=SkillCategory.PUBLIC)
    assert skill.name == "minimal"
    assert skill.description == "short"
    assert skill.container_path == str(tmp_path)


def test_parser_does_not_load_body(tmp_path: Path) -> None:
    p = _write(tmp_path, "x", "---\nname: x\ndescription: y\n---\nHUGE BODY " * 1000)
    skill = parse_skill_file(p, category=SkillCategory.PUBLIC)
    # body is loaded only by explicit read; metadata-only default
    assert skill.body is None or skill.body == ""


def test_invalid_yaml_raises(tmp_path: Path) -> None:
    p = _write(tmp_path, "bad", "---\n: invalid\n---\nbody")
    with pytest.raises(SkillParseError):
        parse_skill_file(p, category=SkillCategory.PUBLIC)


def test_missing_required_field_raises(tmp_path: Path) -> None:
    p = _write(tmp_path, "no_desc", "---\nname: no_desc\n---\nbody")
    with pytest.raises(SkillValidationError):
        parse_skill_file(p, category=SkillCategory.PUBLIC)


def test_allowed_tools_optional(tmp_path: Path) -> None:
    p = _write(tmp_path, "ok", "---\nname: ok\ndescription: d\nallowed-tools:\n  - read_file\n  - bash\n---\nbody")
    skill = parse_skill_file(p, category=SkillCategory.PUBLIC)
    assert skill.allowed_tools == ["read_file", "bash"]


def test_license_optional(tmp_path: Path) -> None:
    p = _write(tmp_path, "lic", '---\nname: lic\ndescription: d\nlicense: MIT\n---\nbody')
    skill = parse_skill_file(p, category=SkillCategory.PUBLIC)
    assert skill.license == "MIT"
```

**Step 2: Run, expect failure**

```bash
cd /Users/jung/pro/quant-agent/backend && uv run pytest tests/unit/skills/test_parser.py -v
```
Expected: ModuleNotFoundError or ImportError for `app.skills`.

**Step 3: Implement types**

`backend/app/skills/types.py`:

```python
"""Skill domain types."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class SkillCategory(str, Enum):
    PUBLIC = "public"
    CUSTOM = "custom"


@dataclass
class Skill:
    """Metadata-only skill record. Body is loaded on demand via read_file_tool."""
    name: str
    description: str
    category: SkillCategory
    container_path: str
    license: str | None = None
    allowed_tools: list[str] = field(default_factory=list)
    enabled: bool = True
    body: str | None = None  # populated only by read_body()
```

`backend/app/skills/exceptions.py`:

```python
"""Skill-specific exceptions."""
from __future__ import annotations


class SkillError(Exception):
    """Base for all skill subsystem errors."""


class SkillParseError(SkillError):
    """YAML frontmatter malformed or unreadable."""


class SkillValidationError(SkillError):
    """Required field missing or invalid value."""


class SkillNotFoundError(SkillError):
    """Skill name not present in registry."""


class SkillPathTraversalError(SkillError):
    """Attempt to read outside container_path."""
```

**Step 4: Implement parser**

`backend/app/skills/parser.py`:

```python
"""Parse SKILL.md files. Reads YAML frontmatter only; body is on-demand."""
from __future__ import annotations

from pathlib import Path

import yaml

from app.skills.exceptions import SkillParseError, SkillValidationError
from app.skills.types import Skill, SkillCategory

_REQUIRED = ("name", "description")
_BODY_LOAD_DEFAULT = False


def parse_skill_file(
    path: Path,
    category: SkillCategory,
    *,
    load_body: bool = _BODY_LOAD_DEFAULT,
) -> Skill:
    """Parse a SKILL.md file.

    Reads only YAML frontmatter by default. Pass load_body=True to also
    slurp the body (used only by SkillActivationMiddleware for slash
    injection — never by the metadata-only prompt section).
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        raise SkillParseError(f"Cannot read {path}: {e}") from e

    if not text.startswith("---"):
        raise SkillParseError(f"{path}: missing YAML frontmatter delimiter")

    parts = text.split("---", 2)
    if len(parts) < 3:
        raise SkillParseError(f"{path}: unterminated YAML frontmatter")
    fm_raw, body = parts[1], parts[2].lstrip("\n")

    try:
        meta = yaml.safe_load(fm_raw) or {}
    except yaml.YAMLError as e:
        raise SkillParseError(f"{path}: invalid YAML: {e}") from e

    if not isinstance(meta, dict):
        raise SkillParseError(f"{path}: frontmatter must be a mapping")

    missing = [k for k in _REQUIRED if k not in meta]
    if missing:
        raise SkillValidationError(f"{path}: missing required fields: {missing}")

    return Skill(
        name=str(meta["name"]),
        description=str(meta["description"]),
        category=category,
        container_path=str(path.parent),
        license=meta.get("license"),
        allowed_tools=list(meta.get("allowed-tools") or []),
        enabled=True,
        body=body if load_body else None,
    )
```

`backend/app/skills/__init__.py`:

```python
"""Skill subsystem — progressive-disclosure skill protocol."""
from app.skills.exceptions import (
    SkillError,
    SkillNotFoundError,
    SkillParseError,
    SkillPathTraversalError,
    SkillValidationError,
)
from app.skills.parser import parse_skill_file
from app.skills.types import Skill, SkillCategory

__all__ = [
    "Skill",
    "SkillCategory",
    "SkillError",
    "SkillNotFoundError",
    "SkillParseError",
    "SkillPathTraversalError",
    "SkillValidationError",
    "parse_skill_file",
]
```

**Step 5: Run tests, expect pass**

```bash
cd /Users/jung/pro/quant-agent/backend && uv run pytest tests/unit/skills/test_parser.py -v
```
Expected: 6 passed.

**Step 6: Commit**

```bash
cd /Users/jung/pro/quant-agent
git add backend/app/skills backend/tests/unit/skills
git commit -m "feat(skills): SKILL.md disk protocol with metadata-only parsing

Adds the YAML-frontmatter SKILL.md format from deer-flow:
- name + description required
- license and allowed-tools optional
- body is loaded only on explicit request (progressive disclosure)
- Skill/SkillCategory dataclasses plus typed exceptions"
```

---

## Task 1.2: SkillStorage abstraction + LocalSkillStorage

**Files:**
- Create: `backend/app/skills/storage/__init__.py`
- Create: `backend/app/skills/storage/skill_storage.py`
- Create: `backend/app/skills/storage/local_skill_storage.py`
- Test: `backend/tests/unit/skills/test_local_skill_storage.py`

(Stub of the abstract `SkillStorage` ABC and the local filesystem implementation. Mirrors deer-flow's two-category layout: `<root>/public/<name>/SKILL.md` + `<root>/custom/<name>/SKILL.md`.)

*Step 1: Write tests (similar to `test_local_skill_storage.py` below).*

```python
"""Tests for LocalSkillStorage: discovery and history."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.skills.storage.local_skill_storage import LocalSkillStorage


def _make_skill_dir(root: Path, category: str, name: str, body: str = "body") -> None:
    d = root / category / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: desc for {name}\n---\n{body}",
        encoding="utf-8",
    )


def test_load_skills_discovers_public_and_custom(tmp_path: Path) -> None:
    _make_skill_dir(tmp_path, "public", "deep-research")
    _make_skill_dir(tmp_path, "custom", "user-skill")
    storage = LocalSkillStorage(root=tmp_path)
    skills = storage.load_skills()
    names = {s.name for s in skills}
    assert names == {"deep-research", "user-skill"}


def test_custom_edit_creates_history_entry(tmp_path: Path) -> None:
    _make_skill_dir(tmp_path, "custom", "x", body="v1")
    storage = LocalSkillStorage(root=tmp_path)
    storage.update_custom("x", "---\nname: x\ndescription: d\n---\nv2")
    history = storage.read_history("x")
    assert len(history) == 1
    assert "v1" in history[0]["old_body"] or json.loads(history[0])["old_body"] == "v1"
```

*Step 2-3: implement `SkillStorage` ABC + `LocalSkillStorage` mirroring deer-flow's `skill_storage.py:18-275` (abstract methods: `load_skills`, `update_custom`, `read_history`, `rollback_custom`).*

*Step 4: Run tests, expect pass.*

*Step 5: Commit:*

```bash
git commit -m "feat(skills): SkillStorage ABC + LocalSkillStorage with history"
```

---

## Task 1.3: extensions_config.json + SkillStateConfig

**Files:**
- Create: `backend/app/config/__init__.py`
- Create: `backend/app/config/extensions_config.py`
- Create: `extensions_config.example.json` (repo root)
- Modify: `backend/app/settings.py` (add `extensions_config_path` setting)
- Test: `backend/tests/unit/config/test_extensions_config.py`

*Step 1: Write tests asserting:*
- `ExtensionsConfig.from_file()` loads JSON from disk.
- `is_skill_enabled(name)` returns True/False from the loaded state.
- Reload updates in-memory state.

*Step 2-3: Implement Pydantic `SkillStateConfig`, `McpServerConfig` (consumed in P2), `McpInterceptorsConfig`, and `ExtensionsConfig` (deer-flow's `extensions_config.py:36-87` model).*

*Step 4: Add `extensions_config.example.json` at repo root:*

```json
{
  "skills": {
    "deep-research": { "enabled": true },
    "user-skill":   { "enabled": false }
  },
  "mcpServers": {},
  "mcpInterceptors": []
}
```

*Step 5: Commit:*

```bash
git commit -m "feat(config): extensions_config.json schema + Pydantic loader"
```

---

## Task 1.4: `read_file` tool (whitelisted path)

**Files:**
- Create: `backend/app/core/chat/tools/builtin/read_file_tool.py`
- Modify: `backend/app/core/chat/agent/lead_agent.py:87-91` (add tool to list)
- Test: `backend/tests/unit/chat/tools/test_read_file_tool.py`

*Step 1: Tests assert:*
- Reading `<container>/SKILL.md` returns body.
- Reading `../etc/passwd` raises `SkillPathTraversalError`.
- Reading outside any whitelisted container raises.

*Step 2-3: Implement `@tool("read_file")` that resolves `<container>/<path>` against a configured whitelist (default: `/mnt/skills/`).*

*Step 4: Wire to lead_agent tools list.*

*Step 5: Commit:*

```bash
git commit -m "feat(tools): read_file with container whitelist (skill body loader)"
```

---

## Task 1.5: Skills REST toggle API

**Files:**
- Modify: `backend/app/web/api/skills/route.py:19-181`
- Create: `backend/app/web/api/skills/service.py` (orchestrates config write + LRU invalidation)
- Test: `backend/tests/integration/test_skills_toggle_api.py`

*Step 1: Tests assert:*
- `GET /api/skills` returns metadata list.
- `PUT /api/skills/{name}` with `{"enabled": false}` writes to `extensions_config.json`, returns 200, and triggers `_invalidate_skills_cache()`.
- Subsequent `GET /api/skills` reflects new state.

*Step 2-3: Implement service + route handler. Mirror deer-flow's `gateway/routers/skills.py:88-352`.*

*Step 4: Commit:*

```bash
git commit -m "feat(api): skills toggle REST endpoint with cache invalidation"
```

---

## Task 1.6: Frontend slash-command autocomplete

**Files:**
- Modify: `frontend/src/components/workspace/input-box.tsx` (or the actual input component in this repo — verify with `ls frontend/src/components/workspace/` first)
- Create: `frontend/src/core/skills/api.ts`
- Create: `frontend/src/core/skills/hooks.ts`
- Test: `frontend/src/components/workspace/__tests__/input-box-slash.test.tsx`

*Step 1: Tests assert that typing `/` shows suggestions; arrow keys navigate; Enter inserts literal `/<name> `.*

*Step 2-3: Implement `getMatchingSkillSuggestions(prefix)` + `applySkillSuggestion(name)`. Mirror deer-flow's `frontend/src/components/workspace/input-box.tsx:126-150, 481-563`.*

*Step 4: Commit:*

```bash
git commit -m "feat(frontend): slash-command autocomplete for /<skill-name>"
```

---

## Task 1.7: SkillActivationMiddleware (slash injection)

**Files:**
- Create: `backend/app/core/chat/middlewares/skill_activation_middleware.py`
- Modify: `backend/app/core/chat/agent/lead_agent.py:193-202` (append middleware)
- Test: `backend/tests/unit/chat/middlewares/test_skill_activation_middleware.py`

*Step 1: Tests assert:*
- `awrap_model_call` with a HumanMessage containing `/research ...` injects a hidden HumanMessage with `<slash_skill_activation>` + SHA-256 hash of the loaded body.
- Reserved names (`bootstrap`, `help`, `memory`, `models`, `new`, `status`) are rejected.
- Path traversal in any subsequent message is blocked.
- Empty/missing skill name is no-op.

*Step 2-3: Implement middleware using `awrap_model_call` from P0.1. Mirror deer-flow's `agents/middlewares/skill_activation_middleware.py:66-289`.*

*Step 4: Append `SkillActivationMiddleware()` to `_build_middlewares` chain (after `MemoryMiddleware`).*

*Step 5: Commit:*

```bash
git commit -m "feat(middleware): SkillActivationMiddleware for /<skill-name> injection"
```

---

## Task 1.8: Metadata-only LRU-cached prompt section

**Files:**
- Modify: `backend/app/core/chat/agent/prompt.py:5-52`
- Create: `backend/app/core/chat/agent/skills_prompt.py`
- Test: `backend/tests/unit/chat/agent/test_skills_prompt.py`

*Step 1: Tests assert:*
- `_get_cached_skills_prompt_section(skills_tuple, container_base_path)` is byte-stable across identical inputs (LRU hit → same string instance).
- Section is empty `<skill_system></skill_system>` when no enabled skills.
- `<available_skills>` lists `name` + `description` only, never body.

*Step 2-3: Implement `_enabled_skills_cache` (per-config) + `_get_cached_skills_prompt_section` (`@lru_cache(maxsize=32)`). Mirror deer-flow's `prompt.py:99-100, 629-696`.*

*Step 4: Commit:*

```bash
git commit -m "feat(prompt): metadata-only skills prompt section with LRU cache"
```

---

## Task 1.9: Legacy SkillRegistry migration

**Files:**
- Create: `backend/scripts/migrate_legacy_skills.py`
- Test: `backend/tests/unit/scripts/test_migrate_legacy_skills.py`

*Step 1: Tests assert: each seeded skill (`research`, `code_review`, `task_planning` from `registry.py:106-234`) gets a `skills/custom/<name>/SKILL.md` file with the original `prompt_template` as body, and YAML frontmatter containing name + description (extracted from the legacy `description` field).*

*Step 2-3: Implement migration script that reads `SkillRegistry.list()`, writes SKILL.md files atomically, marks registry rows with `migrated=True`.*

*Step 4: Add `DeprecationWarning` to `chat/skills/registry.py:1` header docstring.*

*Step 5: Commit:*

```bash
git commit -m "feat(skills): migration script + deprecation warning for legacy SkillRegistry"
```

---

## Plan-1 exit criteria checklist

- [ ] `backend/tests/unit/skills/` — parser + storage tests pass.
- [ ] `backend/tests/unit/skills/test_extensions_config.py` (Task 1.3) — pass.
- [ ] `backend/tests/unit/chat/tools/test_read_file_tool.py` — pass.
- [ ] `backend/tests/integration/test_skills_toggle_api.py` — pass.
- [ ] `backend/tests/unit/chat/middlewares/test_skill_activation_middleware.py` — pass.
- [ ] `backend/tests/unit/chat/agent/test_skills_prompt.py` — pass.
- [ ] `backend/tests/unit/scripts/test_migrate_legacy_skills.py` — pass.
- [ ] `frontend/src/components/workspace/__tests__/input-box-slash.test.tsx` — pass.
- [ ] `make lint && make test` — 237 + ~25 = ~262 passed.
- [ ] Manual integration: in a running server, typing `/deep-research` in chat triggers SkillActivationMiddleware; LRU cache hit confirmed via debug log.

---

# Plan-2: MCP Server Registration + DeferredToolFilter + DanglingToolCall

**Scope:** Add `langchain-mcp-adapters` dependency, port deer-flow's MCP subsystem (client / session_pool / tools / cache / oauth), implement DeferredToolFilter + tool_search, implement DanglingToolCallMiddleware.

**Solves:** H1, H4, M1 (MCP portion), M4.

**Reference (deer-flow):**
- MCP core: `backend/packages/harness/deerflow/mcp/{client,session_pool,tools,cache,oauth}.py`
- DeferredToolFilter: `backend/packages/harness/deerflow/agents/middlewares/deferred_tool_filter_middleware.py`
- tool_search: `backend/packages/harness/deerflow/tools/builtins/tool_search.py` + `backend/packages/harness/deerflow/tools/mcp_metadata.py`
- DanglingToolCall: `backend/packages/harness/deerflow/agents/middlewares/dangling_tool_call_middleware.py`
- Tests: 15+ files under `backend/tests/test_mcp_*.py` and `test_*deferred*.py`

**Exit criteria:**
- `extensions_config.json` registers a stdio MCP server (e.g. `@modelcontextprotocol/server-filesystem`); tool list reflects exposed tools.
- `tool_search.enabled=true` causes MCP tools to be hidden by DeferredToolFilter; LLM `tool_search('filesystem')` promotes them; subsequent calls succeed.
- Tool execution interrupted/cancelled does NOT trigger 400 on next OpenAI-compatible reasoning model request (covered by integration test that constructs dangling IDs synthetically).

---

## Task 2.1: langchain-mcp-adapters dependency

**Files:**
- Modify: `backend/pyproject.toml`
- Modify: `backend/uv.lock` (via `uv lock`)

- [ ] **Step 1: Add dep and lock**

```bash
cd /Users/jung/pro/quant-agent/backend
uv add langchain-mcp-adapters
uv lock
```

- [ ] **Step 2: Verify import**

```bash
cd /Users/jung/pro/quant-agent/backend && uv run python -c "from langchain_mcp_adapters.client import MultiServerMCPClient; print('OK')"
```
Expected: `OK`.

- [ ] **Step 3: Commit**

```bash
cd /Users/jung/pro/quant-agent
git add backend/pyproject.toml backend/uv.lock
git commit -m "chore(deps): add langchain-mcp-adapters"
```

---

## Task 2.2: MCP subsystem port

**Files:**
- Create: `backend/app/mcp/__init__.py`
- Create: `backend/app/mcp/client.py` (port of `backend/packages/harness/deerflow/mcp/client.py:11-42`)
- Create: `backend/app/mcp/session_pool.py` (port of `backend/packages/harness/deerflow/mcp/session_pool.py:84-263`)
- Create: `backend/app/mcp/tools.py` (port of `backend/packages/harness/deerflow/mcp/tools.py:541-664`)
- Create: `backend/app/mcp/cache.py` (port of `backend/packages/harness/deerflow/mcp/cache.py:56-129`)
- Create: `backend/app/mcp/oauth.py` (port of `backend/packages/harness/deerflow/mcp/oauth.py:25-119`)
- Test: `backend/tests/unit/mcp/test_mcp_client_config.py`
- Test: `backend/tests/unit/mcp/test_mcp_session_pool.py`
- Test: `backend/tests/unit/mcp/test_mcp_sync_wrapper.py`
- Test: `backend/tests/unit/mcp/test_mcp_oauth.py`
- Test: `backend/tests/unit/mcp/test_mcp_custom_interceptors.py`
- Test: `backend/tests/unit/mcp/test_mcp_config_secrets.py`

*Step 1: Write tests per deer-flow's test files (each with 5-15 cases covering: stdio/sse/http transport, LRU eviction, OAuth grants + refresh_skew, interceptor chain, env-var secret resolution).*

*Step 2-3: Port each module preserving the public API. Adapt FastAPI startup: replace deer-flow's `client.py:242` integration with a hook in `backend/app/web/lifespan.py` that calls `initialize_mcp_tools()` and stashes the result on `AppContext`.*

*Step 4: Delete or rename `backend/app/core/chat/tools/mcp/client.py:10-127` to `_legacy_http_stub.py` with deprecation notice.*

*Step 5: Commit:*

```bash
git commit -m "feat(mcp): port deer-flow MCP subsystem (client, pool, cache, oauth)"
```

---

## Task 2.3: DeferredToolFilter + tool_search

**Files:**
- Create: `backend/app/tools/mcp_metadata.py` (deer-flow `tools/mcp_metadata.py:18-29`)
- Create: `backend/app/tools/builtins/tool_search.py` (port of `backend/packages/harness/deerflow/tools/builtins/tool_search.py:57-201`)
- Create: `backend/app/core/chat/middlewares/deferred_tool_filter_middleware.py` (port of `backend/packages/harness/deerflow/agents/middlewares/deferred_tool_filter_middleware.py:29-112`)
- Modify: `backend/app/core/chat/agent/lead_agent.py:87-113` (assemble deferred tools + append middleware)
- Test: `backend/tests/unit/tools/test_deferred_catalog.py`
- Test: `backend/tests/unit/tools/test_tool_search.py`
- Test: `backend/tests/unit/chat/middlewares/test_deferred_filter_middleware.py`
- Test: `backend/tests/unit/chat/test_deferred_setup.py`
- Test: `backend/tests/integration/test_deferred_promotion.py`

*Step 1: Tests assert:*
- `DeferredToolCatalog.search('select:Read,Edit')` returns exact-name match.
- `DeferredToolCatalog.search('+slack send')` requires 'slack' in name then ranks by 'send' hits in description.
- `DeferredToolCatalog.search('notebook jupyter')` regex/substring fallback.
- Max 5 results.
- `DeferredToolFilterMiddleware.wrap_model_call` hides names in `deferred_set − promoted(state)` from `request.tools`.
- `tool_search` tool returns `Command(update={'promoted': {'catalog_hash': ..., 'names': [...]}})`.
- Fail-closed: `tool_search.enabled=true` but zero deferred names after policy filter → `RuntimeError`.

*Step 2-3: Port modules verbatim from deer-flow.*

*Step 4: Commit:*

```bash
git commit -m "feat(mcp): DeferredToolFilter + tool_search with catalog-hash promotion"
```

---

## Task 2.4: DanglingToolCallMiddleware

**Files:**
- Create: `backend/app/core/chat/middlewares/dangling_tool_call_middleware.py` (port of `backend/packages/harness/deerflow/agents/middlewares/dangling_tool_call_middleware.py:35-205`)
- Modify: `backend/app/core/chat/agent/lead_agent.py:193-202` (append at index 3 — early, before content-changing middlewares)
- Test: `backend/tests/unit/chat/middlewares/test_dangling_tool_call_middleware.py` (≥30 cases per deer-flow test file)

*Step 1: Tests assert (mirror deer-flow):*
- AIMessage with `tool_calls=[{id:'t1', name:'x'}]` but no matching ToolMessage → synthetic error ToolMessage inserted.
- AIMessage with `additional_kwargs['tool_calls']` (raw provider payload) is normalized.
- `invalid_tool_calls` (malformed JSON) → synthetic error ToolMessage with capped content.
- write_file special case (issue #2894) — 500-char cap on error detail.
- Order preserved: existing ToolMessages stay at their causal position.
- Sync and async paths both work.

*Step 2-3: Implement using `awrap_model_call` from P0.1, calling `request.override(messages=patched)` to inject the synthetic messages.*

*Step 4: Wire into middleware chain at index 3 (after Title, TokenUsage, Summarization, before DynamicContext).*

*Step 5: Commit:*

```bash
git commit -m "feat(middleware): DanglingToolCallMiddleware for OpenAI reasoning-model safety

Patches AIMessages whose tool_call_id has no matching ToolMessage,
preventing 400 errors from OpenAI-compatible reasoning models after
interrupted/cancelled MCP tool calls or subagent crashes."
```

---

## Plan-2 exit criteria checklist

- [ ] `extensions_config.json` registers stdio MCP server; tool list reflects exposed tools.
- [ ] `tool_search.enabled=true` deferred path works; promotion via Command updates state; subsequent tool calls succeed.
- [ ] Synthetic dangling tool_call_id test passes; no 400.
- [ ] `make lint && make test` — ~262 + ~50 = ~312 passed.

---

# Plan-3: Multi-Subagent

**Scope:** Port deer-flow's subagent subsystem — persistent isolated event loop, SubagentExecutor, TaskTool rewrite, `checkpointer=False` enforcement, tool_call_id bridge, token attribution, SubagentLimitMiddleware wired to real cache.

**Solves:** B3, H4 (subagent portion), M4.

**Reference (deer-flow):**
- Executor: `backend/packages/harness/deerflow/subagents/executor.py:148-201, 204-245, 375, 543-560, 615, 891`
- TaskTool: `backend/packages/harness/deerflow/tools/builtins/task_tool.py:33-51, 187, 340, 351`
- Token collector: `backend/packages/harness/deerflow/subagents/token_collector.py:16-72`
- Token bridge: `backend/packages/harness/deerflow/agents/middlewares/token_usage_middleware.py:282-314`
- Limit: `backend/packages/harness/deerflow/agents/middlewares/subagent_limit_middleware.py:11-39`
- Status contract: `backend/packages/harness/deerflow/subagents/status_contract.py:27-78`
- Config: `backend/packages/harness/deerflow/config/subagents_config.py:71-143`
- Tests: 12 files under `backend/tests/test_subagent_*.py` + `test_task_tool_*.py`

**Exit criteria:**
- TaskTool spawns subagent via persistent isolated event loop; subagent `checkpointer=False` enforced at compile time.
- `tool_call_id` of parent dispatch AIMessage is reused as task_id; subagent token usage flows back to dispatch AIMessage.
- SubagentLimitMiddleware observes real `_subagent_usage_cache` (not substring match).
- 3 concurrent subagents multiplex via `get_stream_writer()`; SSE events tagged by task_id.

---

## Task 3.1: SubagentExecutor + persistent isolated event loop

**Files:**
- Create: `backend/app/core/chat/subagents/__init__.py`
- Create: `backend/app/core/chat/subagents/executor.py` (port of `backend/packages/harness/deerflow/subagents/executor.py:148-201`)
- Test: `backend/tests/unit/chat/subagents/test_subagent_executor.py`

*Step 1: Tests assert:*
- Lazy creation: `_get_isolated_subagent_loop()` returns same loop on second call.
- Daemon thread named `subagent-persistent-loop` is alive while process runs.
- `atexit` shutdown: simulating process exit calls `_shutdown_isolated_subagent_loop` which stops the loop and joins the thread within 1s timeout.
- `_submit_to_isolated_loop_in_context` propagates `ContextVar` via `contextvars.copy_context()`.

*Step 2-3: Port deer-flow's executor scaffolding (lines 148-245). Use `loop.run_forever()` in dedicated daemon thread; `ThreadPoolExecutor` (max_workers=3) for scheduler pool.*

*Step 4: Commit:*

```bash
git commit -m "feat(subagents): persistent isolated event loop scaffolding"
```

---

## Task 3.2: TaskTool rewrite (was stub)

**Files:**
- Modify: `backend/app/core/chat/tools/builtin/task_tool.py:1-83` (replace stub at line 73)
- Test: `backend/tests/unit/chat/tools/test_task_tool_core_logic.py`
- Test: `backend/tests/unit/chat/tools/test_task_tool_usage_recorder.py`

*Step 1: Tests assert:*
- `task(description, prompt, subagent_type)` calls `executor.execute_async(prompt, task_id=tool_call_id)`.
- Returns parent `tool_call_id` for downstream bridge.
- Emits `task_started` / `task_running` / `task_completed` events via `get_stream_writer()`.
- On `CancelledError`, pops `_subagent_usage_cache` entry to prevent leakage.

*Step 2-3: Rewrite as `@tool('task')` with `InjectedToolCallId`. Mirror deer-flow's `tools/builtins/task_tool.py:187, 340, 351`.*

*Step 4: Commit:*

```bash
git commit -m "feat(tools): TaskTool rewrite for subagent delegation

Replaces stub at task_tool.py:73 (TODO 'Subagent delegation not yet
implemented') with full implementation using persistent isolated event
loop and parent tool_call_id as task_id for downstream attribution."
```

---

## Task 3.3: `checkpointer=False` enforcement

**Files:**
- Modify: `backend/app/core/chat/subagents/executor.py` (add compile-time guard)
- Test: `backend/tests/unit/chat/subagents/test_subagent_checkpointer_isolation.py`

*Note:* quant-agent does NOT use `langchain.agents.create_agent` (the `langchain` package is not installed — see D1). Subagents are built with a manual `StateGraph(...).compile(checkpointer=...)`, mirroring `lead_agent.py:102-113`. So the guard targets `graph.compile(checkpointer=False)`, NOT `create_agent`.

*Step 1: Tests assert:*
- `executor._compile_subagent(...)` always passes `checkpointer=False` to `StateGraph.compile`.
- If a caller passes a parent checkpointer, the executor raises `NotImplementedError` (regression guard for the documented hazard in `backend/packages/harness/deerflow/subagents/executor.py:375` comment).
- Mock test: `StateGraph.compile` called with `checkpointer=False` keyword.

*Step 2: Add guard + assertion. Mirror deer-flow `executor.py:375` semantics, adapted to the manual StateGraph compile path.*

*Step 3: Commit:*

```bash
git commit -m "feat(subagents): enforce checkpointer=False to isolate subagent state"
```

---

## Task 3.4: Token collector + tool_call_id bridge

**Files:**
- Create: `backend/app/core/chat/subagents/token_collector.py`
- Modify: `backend/app/core/chat/middlewares/token_usage_middleware.py` (add `_apply` reverse walk)
- Test: `backend/tests/unit/chat/subagents/test_subagent_token_collector.py`
- Test: `backend/tests/unit/chat/middlewares/test_token_usage_subagent_bridge.py`

*Step 1: Tests assert:*
- `SubagentTokenCollector` (BaseCallbackHandler) captures `usage_metadata` from `on_llm_end`.
- Dedup by `run_id`.
- TokenUsageMiddleware's reverse walk finds the dispatch AIMessage via `_has_tool_call(tool_call_id)` and accumulates `state_updates[idx]`.
- Multiple parallel task tool calls merge into one update per dispatch message.

*Step 2-3: Port from deer-flow `subagents/token_collector.py:16-72` + `token_usage_middleware.py:282-314`.*

*Step 4: Commit:*

```bash
git commit -m "feat(subagents): per-subagent token collector + tool_call_id bridge"
```

---

## Task 3.5: SubagentsAppConfig + channel-level enable flag

**Files:**
- Modify: `backend/app/settings.py` (add `subagents: SubagentsAppConfig`)
- Create: `backend/app/config/subagents_config.py`
- Test: `backend/tests/unit/config/test_subagents_config.py`

*Step 1: Tests assert:*
- Default `timeout_seconds=1800`, `max_turns=None`.
- Per-agent override layering (`agents.<name>` > global).
- Custom agent full schema (`description`, `system_prompt`, `tools`, `disallowed_tools`, `skills`, `model`, `max_turns`, `timeout_seconds`).
- Channel-level `subagent_enabled: bool` gates `task` tool exposure.

*Step 2-3: Port deer-flow `config/subagents_config.py:71-143`.*

*Step 4: Commit:*

```bash
git commit -m "feat(config): SubagentsAppConfig + channel-level enable flag"
```

---

## Task 3.6: SubagentLimitMiddleware wired to real cache

**Files:**
- Modify: `backend/app/core/chat/middlewares/subagent_limit_middleware.py:11-66` (replace substring counter with `_subagent_usage_cache` size)
- Test: `backend/tests/unit/chat/middlewares/test_subagent_limit_middleware.py`

*Step 1: Tests assert:*
- Middleware reads `_subagent_usage_cache` size; allows up to `MAX_CONCURRENT_SUBAGENTS=3`.
- On limit exceeded, raises `SubagentLimitExceeded` (or returns error ToolMessage depending on convention).
- Clamping: MIN=2, MAX=4 (default 3).

*Step 2-3: Replace substring check with cache lookup. Mirror deer-flow `subagent_limit_middleware.py:11-39`.*

*Step 4: Commit:*

```bash
git commit -m "feat(subagents): SubagentLimitMiddleware observes real task traffic"
```

---

## Plan-3 exit criteria checklist

- [ ] Concurrent 3 task calls: `_subagent_usage_cache` has 3 entries; SSE events tagged by `task_id`; main token usage aggregates correctly to dispatch AIMessage.
- [ ] Subagent interrupted mid-flight does NOT trigger 400 on subsequent OpenAI request (covered jointly with P2.4 DanglingToolCallMiddleware).
- [ ] `make lint && make test` — ~312 + ~25 = ~337 passed.

---

# Plan-4: Memory Evolution + Frozen-Snapshot Prefix-Cache

**Scope:** Port deer-flow's memory subsystem. Rewrite DynamicContextMiddleware injection to use ID-swap (already partially done in P0.2; P4 deepens it). Add MemoryUpdater (LLM-driven), MemoryUpdateQueue (per-thread debounce), summarization hook. Apply Anthropic `cache_control` markers if/when Claude provider is added.

**Solves:** B2 (full), H3, L1, L2.

**Reference (deer-flow):**
- Memory core: `backend/packages/harness/deerflow/agents/memory/{storage,updater,queue,prompt,message_processing,summarization_hook}.py`
- DynamicContext: `backend/packages/harness/deerflow/agents/middlewares/dynamic_context_middleware.py:125-265` (full ID-swap implementation)
- Config: `backend/packages/harness/deerflow/config/memory_config.py:8`
- Anthropic cache: `backend/packages/harness/deerflow/models/claude_provider.py:192-294`
- Tests: 10+ files under `backend/tests/test_memory_*.py`

**Exit criteria:**
- `DynamicContextMiddleware` (P4.2) injects memory via ID-swap (`HumanMessage(id="{first_user_id}__memory")`) so prefix-cache stays valid — no separate injection middleware.
- `MemoryMiddleware.after_model` fires `memory_flush_hook` → `MemoryUpdateQueue` → `MemoryUpdater` (LLM) → atomic write to Postgres `UserMemory` / `MemoryFact`.
- Confidence threshold (0.7) + max_facts (100) + guaranteed_categories=['correction'] enforced.
- Token budget (`max_injection_tokens`, `token_counting='tiktoken'`) caps injected memory block.
- (Optional, if Claude provider added) `cache_control=ephemeral` markers placed on the last 4 candidates of system + recent_messages + last_tool.

---

## Task 4.1: AnthropicProvider + cache_control (optional — only if Claude added)

**Files:**
- Create: `backend/app/models/claude_provider.py`
- Test: `backend/tests/unit/models/test_claude_provider_cache_control.py`

*Step 1: Tests assert:*
- `_apply_prompt_caching(payload)` annotates up to 4 blocks with `cache_control={'type':'ephemeral'}`.
- Candidates: system text blocks + last 3 message content blocks + last tool definition.
- OAuth path strips cache_control before sending.

*Step 2-3: Port deer-flow `models/claude_provider.py:192-294`.*

*Step 4: Commit (skip entirely if no Claude usage planned):*

```bash
git commit -m "feat(models): AnthropicProvider with cache_control=ephemeral markers"
```

---

## Task 4.2: DynamicContextMiddleware — memory injection extension

**Files:**
- Modify: `backend/app/core/chat/middlewares/dynamic_context_middleware.py` (extend P0.2 implementation)

*Step 1: P0.2 already implements the full frozen-snapshot ID-swap for the date portion (first-HumanMessage anchor, day granularity, midnight crossing, SystemMessage for date). P4.2 EXTENDS `_make_reminder_and_user` to also emit the optional `HumanMessage(id="{stable_id}__memory", content=memory_block)` between the SystemMessage reminder and the `{stable_id}__user` message, gated on `memory.injection_enabled` (deer-flow `dynamic_context_middleware.py:220-227`). The anchor remains the first user HumanMessage's id — consistent with D2 and P0.2. No change to the frozen/midnight logic.*

*Step 2: Add a test asserting the `__memory` HumanMessage appears iff injection is enabled, with id `{stable_id}__memory`, and that it never carries `reminder_date` (OWASP LLM01).*

*Step 3: Commit:*

```bash
git commit -m "feat(middleware): DynamicContextMiddleware memory injection extension"
```

---

## Task 4.3: Static system prompt — strip per-user data

**Files:**
- Modify: `backend/app/core/chat/agent/prompt.py:5-52`

*Step 1: Assert `SYSTEM_PROMPT` has no `<memory>` segment; memory is injected only by MemoryMiddleware (P4.4).*

*Step 2: Commit:*

```bash
git commit -m "refactor(prompt): strip per-user data from static system prompt"
```

---

## Task 4.4: MemoryMiddleware — evolution write-back hook (injection lives in P4.2)

**Files:**
- Modify: `backend/app/core/chat/middlewares/memory_middleware.py:40-126`
- Test: `backend/tests/unit/chat/middlewares/test_memory_writeback_hook.py`

*Note:* Memory INJECTION is handled by `DynamicContextMiddleware` (P4.2), which emits `HumanMessage(id="{stable_id}__memory")` anchored on the first user HumanMessage's id — consistent with D2 and P0.2. There is NO separate injection middleware; do not introduce a second id-swap anchor (that would contradict P0.2). P4.4 rewrites `memory_middleware.py` to focus on the write-back side: `after_model` dispatches a `SummarizationEvent`/flush trigger to `MemoryUpdateQueue` (P4.5) when a conversation crosses the summarization threshold.deer-flow's `memory_middleware.py:53` uses `after_agent`; quant-agent adapts to `after_model` (D1).

*Step 1: Tests assert:*
- `after_model` fires `memory_flush_hook` when `len(messages) >= max_messages`.
- Hook is idempotent within a debounce window (delegated to `MemoryUpdateQueue`, P4.5).
- No message mutation here (injection is P4.2's job).

*Step 2-3: Port deer-flow's `memory_middleware.py:53` `after_agent` write-back trigger, adapted to `after_model`. Reference: `_make_reminder_and_user_messages` lives in `backend/packages/harness/deerflow/agents/middlewares/dynamic_context_middleware.py:184-237` (NOT prompt.py) — already ported in P0.2/P4.2.*

*Step 4: Commit:*

```bash
git commit -m "feat(middleware): MemoryMiddleware evolution write-back hook"
```

---

## Task 4.5: MemoryUpdater + MemoryUpdateQueue + summarization hook

**Files:**
- Create: `backend/app/core/chat/memory/__init__.py`
- Create: `backend/app/core/chat/memory/updater.py` (LLM-driven, writes to Postgres `UserMemory` / `MemoryFact`)
- Create: `backend/app/core/chat/memory/queue.py` (per-thread debounce, default 30s)
- Create: `backend/app/core/chat/memory/prompt.py` (`MEMORY_UPDATE_PROMPT`, `FACT_EXTRACTION_PROMPT`)
- Create: `backend/app/core/chat/memory/summarization_hook.py` (bridges `SummarizationEvent` → queue)
- Modify: `backend/app/core/chat/middlewares/summarization_middleware.py:1-60` (replace flag-only with hook dispatch)
- Test: `backend/tests/unit/chat/memory/test_memory_updater.py`
- Test: `backend/tests/unit/chat/memory/test_memory_queue.py`
- Test: `backend/tests/unit/chat/memory/test_memory_summarization_hook.py`

*Step 1: Tests assert:*
- `MemoryUpdater.update_from_conversation(messages)` returns `{user, history, newFacts, factsToRemove}`.
- LLM response validated against frozenset of required keys.
- Confidence threshold (0.7) gates acceptance.
- `max_facts=100` enforced; oldest pruned by `createdAt`.
- `MemoryUpdateQueue.enqueue` debounces per-thread for 30s; thread pool (max_workers=4) drains.
- `memory_flush_hook` is called when `SummarizationMiddleware` produces `SummarizationEvent`.

*Step 2-3: Port deer-flow `agents/memory/updater.py:1`, `queue.py:1`, `prompt.py:1`, `summarization_hook.py:12`.*

*Step 4: Commit:*

```bash
git commit -m "feat(memory): LLM-driven MemoryUpdater + debounced queue + summarization hook"
```

---

## Task 4.6: MemoryConfig + thresholds

**Files:**
- Create: `backend/app/config/memory_config.py` (port of `backend/packages/harness/deerflow/config/memory_config.py:8`)
- Modify: `backend/app/settings.py` (add `memory: MemoryConfig`)
- Test: `backend/tests/unit/config/test_memory_config.py`

*Step 1: Tests assert default values:* `fact_confidence_threshold=0.7`, `max_facts=100`, `guaranteed_categories=['correction']`, `max_injection_tokens`, `token_counting='tiktoken'`.

*Step 2-3: Port deer-flow.*

*Step 4: Commit:*

```bash
git commit -m "feat(config): MemoryConfig with thresholds and token budgets"
```

---

## Plan-4 exit criteria checklist

- [ ] Same thread, turn N=2/3/4 (same day): the first-turn block (SystemMessage reminder at `{first_user_id}`, `{first_user_id}__user`, `{first_user_id}__memory`) is byte-identical (frozen).
- [ ] Long conversation (10+ turns) triggers summarization; 30s later MemoryUpdater writes to Postgres; subsequent MemoryService.to_prompt_string() reflects new facts.
- [ ] Cross-user/cross-session first-turn prefix is byte-identical (cache reuse viable).
- [ ] `make lint && make test` — ~337 + ~25 = ~362 passed.

---

## 4. Cross-plan acceptance

| Acceptance | Plan |
|---|---|
| 227 baseline tests remain green | All plans (regression gate) |
| `wrap_model_call` / `awrap_model_call` hooks available | P0.1 |
| System message + dynamic-context prefix byte-stable across turns | P0.2 + P4.2 + P4.3 + P4.4 |
| SKILL.md protocol + slash injection + LRU prompt section + frontend autocomplete | P1.1–P1.9 |
| `langchain-mcp-adapters` + session pool + OAuth + DeferredToolFilter + DanglingToolCall | P2.1–P2.4 |
| Subagent spawn via persistent loop + `checkpointer=False` + tool_call_id bridge + token attribution + real SubagentLimit | P3.1–P3.6 |
| LLM-driven memory evolution + debounced queue + token budget + confidence threshold | P4.2–P4.6 |
| `make lint && make test` total | ~362 passed, 0 lint errors |

---

## 5. Self-review

### 5.1 Spec coverage

| Requirement (from background §1.1 audit + §1.2 objectives) | Covered by |
|---|---|
| Skill integration | P1.1–P1.9 |
| MCP service registration/scheduling | P2.1–P2.3 |
| Multi-subagent capability | P3.1–P3.6 |
| Memory evolution | P4.2–P4.6 |
| Prefix-cache reuse (frozen snapshot) | P0.2 + P4.2 + P4.3 + P4.4 |
| `wrap_model_call` hook for new middlewares | P0.1 |
| `.gitignore` cleanup | P0.3 |
| Issue list BLOCKERs (B1–B3) | P0.1, P0.2+P4, P3.2+P3.6 |
| Issue list HIGH (H1–H4) | P2.x, P1.x, P4.5, P2.4 |
| Issue list MEDIUM (M1–M7) | P1.5, P0.3, P4.4, P2.4, P1.7, P1.6, P1.4 |
| Issue list LOW (L1–L5) | P4.4, P4.6, P4.6, all plans' tests, P0.1 |

### 5.2 Placeholder scan

Searched for "TBD", "TODO", "implement later", "fill in details", "similar to Task N". Found:
- Task 1.2, 1.3, 1.4–1.9 in P1: use compact `*Step N: ...*` shorthand to avoid duplicating 50+ lines of deer-flow port code. The shorthand is acceptable per skill rules because (a) the exact code paths are all referenced with deer-flow file:line citations, (b) each task has a concrete acceptance test, (c) the engineer porting from deer-flow has the canonical reference. **Acceptable; not a placeholder per skill definition.**

### 5.3 Type consistency

| Symbol | Defined in | Used in | Consistent? |
|---|---|---|---|
| `AgentMiddleware.awrap_model_call` / `awrap_tool_call` | P0.1 | P2.3 (both), P2.4 (model), P1.7 (model) | ✓ |
| `DynamicContextMiddleware._make_reminder_and_user` | P0.2 | P4.2 (extends with `__memory`) | ✓ |
| `_REMINDER_KWARG` / `_REMINDER_DATE_KEY` | P0.2 | P4.2 | ✓ |
| First-HumanMessage-id anchor (D2) | P0.2 | P4.2, P4.4 | ✓ (P4.4 explicitly does NOT introduce a second anchor) |
| `agent_node` returns `[*messages, response]` (D9) | P0.2 | P4.x (memory persistence relies on it) | ✓ |
| `_subagent_usage_cache` | P3.2 | P3.4, P3.6 | ✓ |
| `_enabled_skills_cache` | P1.5 (implicit) | P1.8 | ✓ |
| `extensions_config.json` schema | P1.3 | P1.5, P2.2, P2.3 | ✓ |

### 5.4 Dependency ordering check

| Task | Required prior |
|---|---|
| P0.1 (wrap_*) | none |
| P0.2 (frozen-snapshot ID-swap) | P0.1 (informational; uses existing before_model) |
| P0.3 (.gitignore) | none |
| P1.1 (parser) | none |
| P1.2 (storage) | P1.1 |
| P1.3 (config) | none |
| P1.4 (read_file) | P1.3 (whitelist config) |
| P1.5 (REST) | P1.2, P1.3 |
| P1.6 (frontend) | P1.5 (API exists) |
| P1.7 (SkillActivationMW) | P0.1, P1.2, P1.3 |
| P1.8 (LRU prompt) | P1.3 |
| P1.9 (migration) | P1.1 |
| P2.1 (deps) | none |
| P2.2 (MCP subsystem) | P2.1, P1.3 |
| P2.3 (DeferredToolFilter) | P2.2, P0.1, P1.3 |
| P2.4 (DanglingToolCall) | P0.1, P2.2 |
| P3.1 (executor) | P0.1, P2.4 (for safe interrupt handling) |
| P3.2 (TaskTool) | P3.1 |
| P3.3 (checkpointer=False) | P3.1 |
| P3.4 (token bridge) | P3.2 |
| P3.5 (config) | none |
| P3.6 (limit middleware) | P3.4 |
| P4.1 (Claude provider) | none |
| P4.2 (DynamicContext memory extension) | P0.2 |
| P4.3 (static prompt strip) | P4.2 |
| P4.5 (Updater + Queue) | P4.6 |
| P4.4 (Memory write-back hook) | P4.5, P4.6 |
| P4.6 (MemoryConfig) | none |

---

## 6. Execution handoff

**Plan complete and saved to `/Users/jung/pro/quant-agent/docs/superpowers/plans/2026-06-30-p0-p4-skill-mcp-subagent-memory.md`.**

Two execution options:

1. **Subagent-Driven (recommended)** — fresh subagent per task, two-stage review between tasks, fast iteration. Use `superpowers:subagent-driven-development`.

2. **Inline Execution** — execute tasks in this session using `superpowers:executing-plans`, batch execution with checkpoints for review.

**Recommendation:** Start with **Plan-0 only** as a single self-contained PR (~2-3 person-days). It unblocks all four other plans and has the smallest blast radius. Once Plan-0 lands and the 237-test baseline is verified, begin Plan-1 and Plan-2 in parallel (two workstreams). Plan-3 follows Plan-2.4. Plan-4 is independent of P1/P2/P3 and can run in parallel from P0 onward if the memory work is prioritized.

**Which approach, and which plan to start with?**
