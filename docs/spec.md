# Quant Agent 功能规格

> 面向 agent 的功能点规格。每个功能点固定三段：输入 → 输出 → 验证。
> 定性（做什么/不做什么）见 `VERSION.md`，本文档只描述当前迭代的功能契约。

## F1 自动生成聚宽策略代码
- 输入：自然语言策略描述（如「ETF 动量轮动」「小市值因子选股」）
- 输出：可直接粘贴聚宽回测的 Python 代码
- 验证：代码通过 `lint_code_tool`；`search_jq_api` / `search_jq_dict` / `search_jq_strategy` 至少被调用一次，或 agent 显式说明跳过理由

## F2 自动回测并返回结果
- 输入：策略代码 + 回测参数（`BacktestParams`：标的、`start_date`/`end_date`、`initial_capital`、`frequency`、`benchmark`）
- 输出：`BacktestResult`，含 `BacktestMetrics`（`annual_return` / `sharpe` / `max_drawdown` / `volatility` / `win_rate` / `total_return` 等）+ 交易明细 + 持仓明细
- 验证：`BacktestStatus` 到达 `DONE`；`metrics` 非 None 且关键字段非空；失败时 `error` 非空且 `status=FAILED`

## F3 调用 skill/mcp 扩展能力
- 输入：用户在 `extensions_config.json` 启用的 MCP server 或 `skills_root` 下的 SKILL.md
- 输出：agent 在对话中可调用对应工具，结果回传给用户
- 验证：MCP 工具经 `get_cached_mcp_tools` 加载并出现在 `tool_search` 白名单；skill 经 `LocalSkillStorage` 解析后注入 system prompt 的 `<skill_system>` 段；调用不报 unknown tool

## F4 安装 skill/mcp 做 deep research
- 输入：skill/mcp 安装指令（SKILL.md 文件或 MCP server 配置）
- 输出：新工具注册后可被 agent 在后续对话调用
- 验证：重启或热加载后工具出现在白名单；`extensions_config.json` 持久化启用状态；调用返回非空结果
