# ADR-0002 Middleware 链设计

- 状态：已采纳
- 关联代码：`backend/app/core/chat/agent/middleware_chain.py`、`backend/app/core/chat/middlewares/`

## 背景

Lead agent 需在同一 model call 前后注入多种横切逻辑（安全、上下文、工具韧性、记忆、限流），且各逻辑有 feature flag 开关、顺序依赖、独立失败域。

## 决策

采用 langchain `AgentMiddleware` 单链，由 `build_middlewares` 按 `RuntimeFeatures` 条件 append，顺序固定（21 级，见 `docs/architecture.md` §5）：

- **顺序依赖**：`DynamicContext`(7) 先于 `JqPrefetch`(8)——JqPrefetch 扫描 `__user` 后缀消息需 DynamicContext 先完成 id 替换；JqPrefetch 产物用 `__jqref` 后缀避免被 DynamicContext 后续轮次重复处理
- **wrap_tool_call 独立栈**：`ToolErrorHandling`(outer) 与 `ToolOutputBudget`(inner) 在 ToolNode 边界形成栈，链中位置仅为可读性，实际调用顺序由 outer/inner 决定
- **Safety/Clarification 始终最后**：safety 终止时剥离 tool_calls 在任何业务逻辑之后
- **条件装配**：缺失 feature 时链缩短，编号非连续；自定义 middleware 经 `custom_middlewares` 在固定注入点（#19）插入

## 结果

- 正面：单一装配点，顺序与开关集中可见；新增 middleware 只改 `build_middlewares`
- 负面：顺序约束隐式（靠代码注释而非类型系统保证）；插入新 middleware 需审计与前后项的 `__suffix` 约定依赖
