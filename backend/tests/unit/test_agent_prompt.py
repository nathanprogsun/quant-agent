"""Unit tests for lead agent system prompt."""

import inspect

from app.core.chat.agent.prompt import SYSTEM_PROMPT, apply_prompt_template


def test_system_prompt_requires_simplified_chinese() -> None:
    assert "简体中文" in SYSTEM_PROMPT
    assert "hi" in SYSTEM_PROMPT or "hello" in SYSTEM_PROMPT
    assert "强制" in SYSTEM_PROMPT


def test_system_prompt_lists_builtin_and_jq_tools() -> None:
    assert "lint_code_tool" in SYSTEM_PROMPT
    assert "validate_strategy_parameters" in SYSTEM_PROMPT
    assert "search_jq_api" in SYSTEM_PROMPT
    assert "search_jq_dict" in SYSTEM_PROMPT
    assert "search_jq_strategy" in SYSTEM_PROMPT
    assert "禁止编造" in SYSTEM_PROMPT or "禁止" in SYSTEM_PROMPT


def test_static_system_prompt_has_no_per_user_memory_segment() -> None:
    # P4.3: per-user <memory> is injected only by DynamicContextMiddleware
    # (P4.2) as a separate HumanMessage; the static system prompt must not
    # carry a <memory> block.
    assert "<memory>" not in SYSTEM_PROMPT


def test_apply_prompt_template_returns_static_prompt_unchanged() -> None:
    prompt = apply_prompt_template()
    assert prompt == SYSTEM_PROMPT
    assert "<memory>" not in prompt


def test_apply_prompt_template_has_no_memory_context_param() -> None:
    # P4.3: per-user memory must not be injectable via the static prompt;
    # memory injection is DynamicContextMiddleware's job (P4.2).
    params = inspect.signature(apply_prompt_template).parameters
    assert "memory_context" not in params
