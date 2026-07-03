"""Middleware assembly factory functions.

Centralizes the middleware chain construction for lead vs. subagent agents.

Pattern (borrowed from deer-flow ``build_middlewares``):
Conditional append — each middleware is added only when its feature flag is
enabled.  Middleware imports are lazy (inside the function body) to avoid a
circular import through ``middlewares/__init__.py``.

Order is preserved:
   1. LLMErrorHandlingMiddleware       — circuit breaker on transport errors
   2. InputSanitizationMiddleware      — prompt-injection defense on user input
   3. DanglingToolCallMiddleware       — patches AIMessage(tool_calls) without ToolMessages
   4. SystemMessageCoalescingMiddleware — collapses adjacent SystemMessages
   5. ToolErrorHandlingMiddleware      — tool exceptions → error ToolMessage (outer wrap_tool_call)
   6. ToolOutputBudgetMiddleware       — cap oversized ToolMessage to disk + head/tail preview (inner)
   7. DynamicContextMiddleware         — injects <system-reminder> date / memory
   8. SkillActivationMiddleware        — /<skill-name> slash injection
   9. TodoMiddleware                   — plan-mode task tracking (conditional)
  10. SummarizationMiddleware          — dispatches memory flush events (conditional)
  11. TokenUsageMiddleware             — accumulates prompt/completion tokens
  12. TitleMiddleware                  — sets the thread title after turn 1
  13. MemoryMiddleware                 — evolution write-back hook (conditional)
  14. DeferredToolFilterMiddleware     — hides deferred MCP tools (conditional)
  15. SubagentLimitMiddleware          — caps concurrent subagent usage (conditional)
  16. LoopDetectionMiddleware          — breaks repetitive tool-call patterns
  17. TokenBudgetMiddleware            — warns / hard-stops on token overuse
  18. <custom_middlewares>             — injection point
  19. SafetyFinishReasonMiddleware     — strips tool calls on safety terminations
  20. ClarificationMiddleware          — terminal interrupt on ask_clarification

Note: ``wrap_tool_call`` hooks (ToolErrorHandling, ToolOutputBudget) form a
stack at the ToolNode boundary regardless of where they sit in the chain;
their relative order (error outer, budget inner) is what matters. The chain
position above is for readability, not call ordering for tool hooks.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain_core.runnables import RunnableConfig

from app.core.chat.agent.features import RuntimeFeatures
from app.skills.storage.local_skill_storage import LocalSkillStorage


def _as_bool(value: bool | AgentMiddleware) -> bool:
    if isinstance(value, bool):
        return value
    return True


def _as_instance(
    default_cls: type[AgentMiddleware[Any, Any, Any]],
    value: bool | AgentMiddleware[Any, Any, Any],
) -> AgentMiddleware[Any, Any, Any]:
    if isinstance(value, AgentMiddleware):
        return value
    return default_cls()


def build_middlewares(
    config: RunnableConfig | None = None,
    *,
    features: RuntimeFeatures,
    available_skills: set[str] | None = None,
    skills_root: str = "skills",
    deferred_setup: Any = None,
    custom_middlewares: list[AgentMiddleware] | None = None,
) -> list[AgentMiddleware]:
    """Build the lead-agent middleware chain from RuntimeFeatures.

    Each middleware is conditionally appended based on its feature flag.
    Imports are lazy to avoid a circular dependency through
    ``middlewares/__init__.py`` (PLC0415 suppressed intentionally).
    """
    # ruff: noqa: PLC0415, I001
    # lazy imports — avoids circular import through middlewares/__init__.py
    from app.core.chat.middlewares.clarification_middleware import ClarificationMiddleware
    from app.core.chat.middlewares.dangling_tool_call_middleware import DanglingToolCallMiddleware
    from app.core.chat.middlewares.deferred_tool_filter_middleware import (
        DeferredToolFilterMiddleware,
    )
    from app.core.chat.middlewares.dynamic_context_middleware import DynamicContextMiddleware
    from app.core.chat.middlewares.input_sanitization_middleware import InputSanitizationMiddleware
    from app.core.chat.middlewares.llm_error_handling_middleware import LLMErrorHandlingMiddleware
    from app.core.chat.middlewares.loop_detection_middleware import LoopDetectionMiddleware
    from app.core.chat.middlewares.memory_middleware import MemoryMiddleware
    from app.core.chat.middlewares.safety_finish_reason_middleware import (
        SafetyFinishReasonMiddleware,
    )
    from app.core.chat.middlewares.skill_activation_middleware import SkillActivationMiddleware
    from app.core.chat.middlewares.subagent_limit_middleware import SubagentLimitMiddleware
    from app.core.chat.middlewares.summarization_middleware import SummarizationMiddleware
    from app.core.chat.middlewares.system_message_coalescing_middleware import (
        SystemMessageCoalescingMiddleware,
    )
    from app.core.chat.middlewares.title_middleware import TitleMiddleware
    from app.core.chat.middlewares.todo_middleware import TodoMiddleware
    from app.core.chat.middlewares.token_budget_middleware import TokenBudgetMiddleware
    from app.core.chat.middlewares.token_usage_middleware import TokenUsageMiddleware

    chain: list[AgentMiddleware[Any]] = []

    # ── 1-4: Always-on foundational middlewares ──────────────
    chain.append(_as_instance(LLMErrorHandlingMiddleware, features.llm_error_handling))
    chain.append(_as_instance(InputSanitizationMiddleware, features.input_sanitization))
    chain.append(_as_instance(DanglingToolCallMiddleware, features.dangling_tool_call))
    chain.append(
        _as_instance(SystemMessageCoalescingMiddleware, features.system_message_coalescing)
    )

    # ── Tool-call resilience (wrap_tool_call stack, outer→inner) ──
    # ToolErrorHandling is added first so it is the OUTER wrapper: it sees
    # exceptions raised by both the handler and ToolOutputBudget (which is
    # defensively coded but cannot be guaranteed crash-free across all
    # filesystem states). ToolOutputBudget runs INNER: it transforms a
    # successful ToolMessage into a head+tail preview before error
    # handling wraps any remaining exception into an error ToolMessage.
    from app.core.chat.middlewares.tool_error_handling_middleware import ToolErrorHandlingMiddleware
    from app.core.chat.middlewares.tool_output_budget_middleware import ToolOutputBudgetMiddleware

    if _as_bool(features.tool_error_handling):
        chain.append(_as_instance(ToolErrorHandlingMiddleware, features.tool_error_handling))
    if _as_bool(features.tool_output_budget):
        if isinstance(features.tool_output_budget, AgentMiddleware):
            chain.append(features.tool_output_budget)
        else:
            from app.settings import get_settings

            chain.append(ToolOutputBudgetMiddleware(output_dir=get_settings().tool_output_dir))

    # ── 5: DynamicContext ────────────────────────────────────
    chain.append(_as_instance(DynamicContextMiddleware, features.dynamic_context))

    # ── 6: SkillActivation ───────────────────────────────────
    if _as_bool(features.skill_activation):
        storage = LocalSkillStorage(root=Path(skills_root))
        chain.append(SkillActivationMiddleware(storage=storage, available_skills=available_skills))

    # ── 7: TodoMiddleware (plan mode) ────────────────────────
    if features.plan_mode:
        chain.append(TodoMiddleware())

    # ── 8: Summarization ─────────────────────────────────────
    if _as_bool(features.summarization):
        chain.append(_as_instance(SummarizationMiddleware, features.summarization))

    # ── 9-10: Always-on tracking middlewares ─────────────────
    chain.append(_as_instance(TokenUsageMiddleware, features.token_usage))
    chain.append(_as_instance(TitleMiddleware, features.title))

    # ── 11: MemoryMiddleware ─────────────────────────────────
    if _as_bool(features.memory):
        chain.append(MemoryMiddleware(max_messages=features.summarization_max_messages))

    # ── 12: DeferredToolFilter ───────────────────────────────
    if _as_bool(features.deferred_tool_filter) and deferred_setup is not None:
        deferred_tool = getattr(deferred_setup, "tool_search_tool", None)
        if deferred_tool is not None:
            chain.append(
                DeferredToolFilterMiddleware(
                    deferred_names=deferred_setup.deferred_names,
                    catalog_hash=deferred_setup.catalog_hash,
                )
            )

    # ── 13: SubagentLimitMiddleware ──────────────────────────
    if features.subagent_enabled:
        chain.append(SubagentLimitMiddleware())

    # ── 14-15: Loop/Token detection ──────────────────────────
    if _as_bool(features.loop_detection):
        chain.append(_as_instance(LoopDetectionMiddleware, features.loop_detection))
    if _as_bool(features.token_budget):
        chain.append(_as_instance(TokenBudgetMiddleware, features.token_budget))

    # ── 16: Custom middleware injection ──────────────────────
    if custom_middlewares:
        chain.extend(custom_middlewares)

    # ── 17-18: Safety + Clarification (always last) ──────────
    if _as_bool(features.safety_finish_reason):
        chain.append(_as_instance(SafetyFinishReasonMiddleware, features.safety_finish_reason))
    if _as_bool(features.clarification):
        chain.append(_as_instance(ClarificationMiddleware, features.clarification))

    return chain


__all__ = ["build_middlewares"]
