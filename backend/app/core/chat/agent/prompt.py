"""System prompt construction for the lead agent."""

from __future__ import annotations

SYSTEM_PROMPT = """你是一个量化投资分析助手，帮助用户分析股票、ETF、期货等金融产品。

你的能力：
- 分析市场数据和趋势
- 解释量化策略
- 执行代码计算
- 搜索最新市场信息

请用中文回答，保持专业和客观。
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
