# ADR-0004 Subagent 状态隔离

- 状态：已采纳
- 关联代码：`backend/app/core/chat/subagents/executor.py`、`backend/app/core/chat/middlewares/subagent_limit_middleware.py`

## 背景

Lead agent 可经 `task_tool` 派发子代理执行并行子任务。子代理与父代理共享 checkpointer 会导致状态污染与 checkpoint 膨胀。

## 决策

- **独立 asyncio loop**：`SubagentExecutor` 在持久隔离 loop 上调度，避免父事件循环阻塞
- **`checkpointer=False`**：子代理图编译时不绑定父 checkpointer，子代理状态不持久化
- **token 独立采集**：`SubagentTokenCollector` 注册为 callback，按 `run_id` 去重，每 LLM end 产出一条 usage 记录
- **并发上限**：`SubagentLimitMiddleware` 观测真实 task 流量，限制同时运行的子代理数

## 结果

- 正面：子代理崩溃/超时不污染父 thread 状态；token 计费独立可追溯
- 负面：子代理无断点续跑能力（无 checkpointer）；取消经 `cancel_event` 协作式，非强制
