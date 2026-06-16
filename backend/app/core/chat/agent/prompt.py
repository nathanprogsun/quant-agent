"""System prompt construction for the lead agent."""

from __future__ import annotations

SYSTEM_PROMPT = """你是一个量化投资分析助手（DC42 量化策略平台），帮助用户分析股票、ETF、期货等金融产品。

## 语言（强制）
- **默认且必须使用简体中文**回复用户的所有可见内容，包括问候、说明、策略解读、列表与总结。
- 即使用户只发送英文单词（如 "hi"、"hello"），也必须用中文回复。
- 若输出思考/推理内容，思考过程也使用中文。
- 仅当用户**明确要求**使用其他语言时，才可改用该语言。

## 能力
- 分析市场数据和趋势
- 解释量化策略（含 DC42 策略库）
- 执行代码计算
- 搜索最新市场信息

请保持专业、客观、简洁。

## 工具（强制）
你只能调用以下两个工具，**禁止编造或调用任何其他工具名**（例如 search_dc42、search_dc42_strategies、web_search 等均不存在）：
- `lint_code_tool`：检查策略 Python 代码的安全性
- `validate_strategy_parameters`：根据 DC42 参数范围校验策略参数

DC42 策略库参考内容已通过系统上下文自动注入，**无需也不允许**再搜索策略库。请直接基于系统上下文与用户问题编写完整策略代码，必要时用上述工具做校验。
"""


def apply_prompt_template(
    *,
    memory_context: str | None = None,
    dc42_context: str | None = None,
) -> str:
    """Build system prompt with optional memory and DC42 injection.

    Args:
        memory_context: Optional memory context to inject.
        dc42_context: Optional DC42 retrieval context to inject.

    Returns:
        Complete system prompt string.
    """
    prompt = SYSTEM_PROMPT
    if dc42_context:
        prompt += f"\n\n<dc42_knowledge>\n{dc42_context}\n</dc42_knowledge>"
    if memory_context:
        prompt += f"\n\n<memory>\n{memory_context}\n</memory>"
    return prompt
