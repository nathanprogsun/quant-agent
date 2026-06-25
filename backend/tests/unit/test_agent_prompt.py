"""Unit tests for lead agent system prompt."""

from app.core.chat.agent.prompt import SYSTEM_PROMPT, apply_prompt_template


def test_system_prompt_requires_simplified_chinese() -> None:
    assert "简体中文" in SYSTEM_PROMPT
    assert "hi" in SYSTEM_PROMPT or "hello" in SYSTEM_PROMPT
    assert "强制" in SYSTEM_PROMPT


def test_system_prompt_lists_builtin_and_jq_tools() -> None:
    assert "lint_code_tool" in SYSTEM_PROMPT
    assert "validate_strategy_parameters" in SYSTEM_PROMPT
    assert "search_jq_api" in SYSTEM_PROMPT
    assert "禁止编造" in SYSTEM_PROMPT or "禁止" in SYSTEM_PROMPT


def test_apply_prompt_template_appends_optional_sections() -> None:
    prompt = apply_prompt_template(
        dc42_context="策略片段",
        memory_context="用户偏好",
    )
    assert SYSTEM_PROMPT.splitlines()[0] in prompt
    assert "<dc42_knowledge>" in prompt
    assert "策略片段" in prompt
    assert "<memory>" in prompt
    assert "用户偏好" in prompt
