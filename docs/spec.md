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
- 输入：未注册用户以 Guest 身份访问平台（无需邮箱/密码），后端自动创建 Guest 账号并签发 session token
- 用户角色：`User.role` 字段（int，默认 `0`）
  - `0` = 超级管理员
  - `1` = 正常用户
  - `2` = Guest
- 回测记录：每次提交回测（不论角色）都在 DB 记录一条回测记录，含 `status`（`success` / `fail`）
- 限额规则：**Guest（`role=2`）每天（UTC 自然日）回测不超过 3 次**，按当日 `status=success` + `status=fail` 的回测记录总数计算
- 输出：
  - Guest 当日第 1–3 次提交 `POST /api/v1/backtest` → 200，正常返回 `backtest_id`，DB 写入回测记录
  - Guest 当日第 4 次提交 → HTTP 429 + 错误码 `backtest_quota_exceeded`，提示"Guest 用户每日回测上限 3 次，请注册账号继续使用"
  - 超级管理员（`role=0`）和正常用户（`role=1`）无限制
- 验证：
  - Guest 当日 3 次成功提交后第 4 次 → 429
  - Guest 当日 3 次中含失败记录（`status=fail`）也计入 3 次限额
  - UTC 次日 00:00 后计数器按回测记录的 `created_at` 自然日重置
  - 注册/登录后 `role` 从 `2` 升级为 `1`，保留原有 thread/backtest 数据，限制解除
  - 限额仅作用于 `POST /api/v1/backtest`，不影响对话、生成策略代码、查看已有回测结果
- 数据模型变更：
  - `users` 表新增 `role: int NOT NULL DEFAULT 0`
  - 新增 `backtest_records` 表：`id` / `user_id` / `backtest_id` / `status`（`success` / `fail`）/ `created_at`
