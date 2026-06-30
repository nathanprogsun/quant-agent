"""System prompt construction for the lead agent.

P4.3: the static system prompt carries NO per-user data. Memory is injected
only by DynamicContextMiddleware (P4.2) as a separate
``HumanMessage(id='{stable_id}__memory')``; it must not live in the system
prompt (that would break the frozen-snapshot prefix cache and conflate
framework-owned vs. user-owned data).

P1.8: optional ``<skill_system>`` block (metadata-only ``(name, description)``
pairs) is appended when ``skills`` is provided (even if empty). When ``skills``
is ``None``, no skills block is emitted (e.g. when skill discovery has not
yet run, or in unit tests).
"""

from __future__ import annotations

from app.core.chat.agent.skills_prompt import _get_cached_skills_prompt_section

SYSTEM_PROMPT = """你是一个量化投资分析助手，帮助用户分析股票、ETF、期货等金融产品。

## 语言（强制）
- **默认且必须使用简体中文**回复用户的所有可见内容，包括问候、说明、策略解读、列表与总结。
- 即使用户只发送英文单词（如 "hi"、"hello"），也必须用中文回复。
- 若输出思考/推理内容，思考过程也使用中文。
- 仅当用户**明确要求**使用其他语言时，才可改用该语言。

## 能力
- 分析市场数据和趋势
- 解释量化策略
- 执行代码计算
- 搜索最新市场信息

请保持专业、客观、简洁。

## 工具（强制）
你只能调用以下工具，**禁止编造或调用任何其他工具名**（例如 web_search 等均不存在）：
- `lint_code_tool`：检查策略 Python 代码的安全性
- `validate_strategy_parameters`：校验策略参数
- `search_jq_api`：检索聚宽 API 文档（get_price、order_target 等函数签名、参数、返回值、环境约束）
- `search_jq_dict`：检索聚宽数据字典（行业 HY、概念 GN、指数、行情字段 close/pe_ratio、代码后缀 .XSHG 等）
- `search_jq_strategy`：检索 2020-2024 聚宽精选策略（ETF 轮动、小市值、因子选股等思路与代码片段）

需要查聚宽 API 函数用法、参数或返回值时，**主动调用** `search_jq_api`。
需要查行业/概念/指数/字段/后缀代码含义时，**主动调用** `search_jq_dict`。
需要参考实战策略范例、ETF 轮动/选股思路或完整代码片段时，**主动调用** `search_jq_strategy`。

编写策略时优先用上述三库工具检索，不要编造 API、字段或策略代码。
"""


def apply_prompt_template(
    *,
    skills: tuple[tuple[str, str], ...] | None = None,
    container_base_path: str | None = None,
) -> str:
    """Build system prompt with optional skills injection.

    Per-user memory is NOT appended here (P4.3); DynamicContextMiddleware
    injects memory as a separate HumanMessage (P4.2). Skills are appended
    (P1.8) when ``skills`` is provided (even if empty). When ``skills`` is
    ``None``, no skills block is emitted (used when skill discovery has not
    run yet, e.g. unit tests).

    Args:
        skills: Optional tuple of ``(name, description)`` pairs — metadata
            only. When provided (even if empty), the cached
            ``<skill_system>`` block is appended.
        container_base_path: Base path of the skill storage; part of the
            LRU key. Defaults to an empty string when ``skills`` is None.

    Returns:
        Complete system prompt string.
    """
    prompt = SYSTEM_PROMPT
    if skills is not None:
        prompt += "\n\n" + _get_cached_skills_prompt_section(skills, container_base_path or "")
    return prompt
