# ADR-0003 DC42 退役与 jq_strategy 接管

- 状态：已采纳
- 日期：2026-06-24（`docs/jq_kb/PLAN.md` §1.4）
- 关联代码：`backend/app/core/chat/agent/prompt.py`、`backend/app/core/jq_kb/tools.py`

## 背景

原 DC42 RAG（`DC42ContextMiddleware` + `dc42/retriever.py`）通过 middleware 自动注入策略到 system prompt，要求 prompt 明确「禁止再搜策略库」。该方式限制 LLM 主动检索能力，且策略来源为平台内部库。

## 决策

退役 DC42，由 `jq_strategy` 库 + `search_jq_strategy` tool 完全替代：

| 维度 | DC42（退役） | jq_strategy（接管） |
|------|-------------|-------------------|
| 策略来源 | 平台内部 DC42 库 | 聚宽社区精选策略（本地 .txt） |
| 注入方式 | middleware 自动注入 system prompt | LLM 主动调用 `search_jq_strategy` |
| 存储 | `backend/data/dc42/chroma_db` | `backend/data/jq_strategy/chroma_db` |

- `prompt.py` SYSTEM_PROMPT 已无 DC42 自动注入段；工具段为 jq 三库白名单
- `lead_agent` middleware 链无 `DC42ContextMiddleware`

## 结果

- 正面：LLM 按需检索，减少无关注入；策略来源透明可控
- 负面：依赖 LLM 主动调用 tool 的可靠性（需 prompt 引导「需要参考实战策略时调用 search_jq_strategy」）
- 旧 `backend/data/dc42/` 数据目录不再维护
