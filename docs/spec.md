# Quant Agent 功能规格

> 面向 agent 的功能点规格。每个功能点固定三段：输入 → 输出 → 验证。
> 定性（做什么/不做什么）见 `VERSION.md`，本文档只描述当前迭代的功能契约。

## F1 自动生成聚宽策略代码
- 输入：自然语言策略描述（如「ETF 动量轮动」「小市值因子选股」）
- 输出：可直接粘贴聚宽回测的 Python 代码
- 验证：代码通过 `lint_code_tool`；`search_jq_api` / `search_jq_dict` / `search_jq_strategy` 至少被调用一次，或 agent 显式说明跳过理由

## F2 自动回测并返回结果
- 输入：策略代码 + 回测参数（`BacktestParams`：标的、`start_date`/`end_date`、`initial_capital`、`frequency`、`benchmark`）
- 输出：`BacktestResult`，含 `BacktestMetrics`（`annual_return` / `sharpe` / `max_drawdown` / `volatility` / `win_rate` / `total_return` 等）+ 收益概况性能曲线（`overallReturn` / `benchmark`）
- 验证：`BacktestStatus` 到达 `DONE`；`metrics` 非 None 且关键字段非空；失败时 `error` 非空且 `status=FAILED`

## F3 调用 skill/mcp 扩展能力
- 输入：用户在 `extensions_config.json` 启用的 MCP server 或 `skills_root` 下的 SKILL.md
- 输出：agent 在对话中可调用对应工具，结果回传给用户
- 验证：MCP 工具经 `get_cached_mcp_tools` 加载并出现在 `tool_search` 白名单；skill 经 `LocalSkillStorage` 解析后注入 system prompt 的 `<skill_system>` 段；调用不报 unknown tool

## F4 安装 skill/mcp 做 deep research
- 输入：skill/mcp 安装指令（SKILL.md 文件或 MCP server 配置）
- 输出：新工具注册后可被 agent 在后续对话调用
- 验证：重启或热加载后工具出现在白名单；`extensions_config.json` 持久化启用状态；调用返回非空结果

## F5 Guest 账号每日回测限额
- 输入：未注册用户以 Guest 身份访问平台（无需邮箱/密码），Guest 身份由后端在首次访问时自动创建并签发短期 session token
- 输出：Guest 用户可使用全部对话/生成策略/回测功能，但**每天（UTC 自然日）最多点击运行策略 5 次**；超额时返回 HTTP 429 + 错误码 `backtest_quota_exceeded`，提示"Guest 用户每日回测上限 5 次，请注册账号继续使用"
- 验证：
  - Guest 用户当日第 1–5 次提交 `POST /api/v1/backtest` → 200，正常返回 `backtest_id`
  - Guest 用户当日第 6 次提交 → 429 `backtest_quota_exceeded`
  - UTC 次日 00:00 后计数器重置 → 首次提交恢复 200
  - 注册用户（非 Guest）无此限制
  - 计数维度：per-user per-day，按 UTC 自然日切分，持久化到 DB（重启不丢）
- 约束：
  - Guest 账号 `is_active=True`、`is_superuser=False`，`User.role` 字段新增 `guest` 值（或新增 `is_guest: bool` 列）
  - Guest session token 过期时间 ≤ 24h；注册/登录后升级为正式用户，保留原有 thread/backtest 数据
  - 限额仅作用于 `POST /api/v1/backtest`（提交回测），不影响对话、生成策略代码、查看已有回测结果
