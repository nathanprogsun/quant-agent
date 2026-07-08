# Quant Agent 架构

> 面向 agent 的系统结构说明。功能契约见 `docs/spec.md`，定性目标见 `VERSION.md`。

## 1. 系统拓扑

```
┌─────────────────────────────────────────────────────────────┐
│  Frontend (Next.js + TypeScript)                            │
│  Workspace UI · Thread/Run 管理 · Backtest 面板              │
│  SSE 消费: chat=fetch+ReadableStream; backtest=EventSource  │
└──────────────────────────┬──────────────────────────────────┘
                           │ HTTP / SSE (经 Next.js route 代理 → FastAPI)
┌──────────────────────────▼──────────────────────────────────┐
│  FastAPI Web 层                                             │
│  Routers: auth · thread · backtest · skills · memory        │
│  Middleware: CORS · AuthMiddleware · exception handlers     │
│  Lifespan: AppContext 装配 (DB / checkpointer / MCP / 内存)│
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│  Core 业务层                                                │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ chat/agent  Lead Agent (LangGraph StateGraph)       │    │
│  │   agent_node ──conditional──▶ tool_node ──▶ agent   │    │
│  │   21 级 middleware 链 (见 §5)                       │    │
│  ├─────────────────────────────────────────────────────┤    │
│  │ chat/tools  builtin(lint/validate/readfile) · jq_kb │    │
│  │              MCP(deferred + tool_search)             │    │
│  ├─────────────────────────────────────────────────────┤    │
│  │ backtest/   BacktestService → jqcli API             │    │
│  │             worker 轮询 · jqcli_auth 登录态         │    │
│  ├─────────────────────────────────────────────────────┤    │
│  │ jq_kb/      3 库 hybrid 检索 (见 §4)                │    │
│  ├─────────────────────────────────────────────────────┤    │
│  │ mcp/        session_pool · client · oauth · cache   │    │
│  ├─────────────────────────────────────────────────────┤    │
│  │ skills/     LocalSkillStorage (SKILL.md 协议)       │    │
│  ├─────────────────────────────────────────────────────┤    │
│  │ chat/memory  MemoryUpdateQueue · updater · provider │    │
│  ├─────────────────────────────────────────────────────┤    │
│  │ chat/subagents  SubagentExecutor (独立 loop + 图)   │    │
│  └─────────────────────────────────────────────────────┘    │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│  数据层                                                     │
│  SQLite(aiosqlite) ─ user/thread/run/memory + checkpointer │
│  ChromaDB ─ jq_api / jq_dict / jq_strategy 向量检索         │
│  BM25 pickle ─ 稀疏检索 (jq_api/jq_dict 已生成; jq_strategy 可选未生成)│
│  远程 Embedding API (OpenAI-compatible /embeddings)        │
│  本地 Reranker ─ bge-reranker-large (SentenceTransformer; 远程备选)│
└─────────────────────────────────────────────────────────────┘
```

> Kùzu 图谱见 `docs/jq_kb/PLAN.md` 计划，代码尚未实现；当前 jq_strategy 仅 ChromaDB + BM25。

## 2. 组件职责

**Web 层**
- `web/application.py` — FastAPI 工厂，注册路由与异常处理
- `web/lifespan.py` — 启动装配 `AppContext`（DB engine、checkpointer、MCP 工具、内存子系统、backtest registry、`warm_up_models`）；关闭时逆序释放
- `web/api/thread/` — thread CRUD + run 创建 + SSE 消费（`sse_consumer`）；run 由 `RunManager` 管理并发与取消
- `web/api/backtest/` — 回测提交/查询/中止，`worker` 后台轮询 jqcli
- `web/api/skills/`、`web/api/memory/` — skill 元数据查询与 memory CRUD
- `web/middleware/auth_middleware.py` — JWT 校验，白名单路由放行

**Agent 层**
- `chat/agent/lead_agent.py` — `make_lead_agent` 工厂：组装 model + tools + system_prompt + middleware，编译为 `CompiledStateGraph`；`make_lead_agent_async` 异步预取 MCP 工具
- `chat/agent/middleware_chain.py` — `build_middlewares` 按 `RuntimeFeatures` 条件装配 21 级链
- `chat/agent/prompt.py` — 静态 system prompt（无 per-user 数据）；`apply_prompt_template` 追加 `<skill_system>` 段与 deferred tool 名
- `chat/agent/thread_state.py` — `ThreadState`（LangGraph 状态 schema）

**工具**
- `chat/tools/builtin/` — `lint_code_tool`、`make_validate_parameters_tool`、`ReadFileTool`（lead_agent 实际装配）；`task_tool`/`bash_tool` 存在但未装配到 lead_agent
- `core/jq_kb/tools.py` — `search_jq_api` / `search_jq_dict` / `search_jq_strategy`（`@tool`，`get_tools(pr_phase=3)` 返回）
- `mcp/tools.py` — `get_cached_mcp_tools`：按 server 独立 gather，broken server 不阻塞；stdio 工具经 session_pool 复用
- `tools/builtins/tool_search.py` — deferred tool 发现：白名单注入 prompt，运行时 `tool_search` 按需加载

**回测**
- `core/backtest/service.py` — 封装 jqcli `run_backtest` / `get_backtest_result` / `get_backtest_logs`，统一错误映射；`_executor` ThreadPoolExecutor(max_workers=4)
- `core/backtest/worker.py` — `run_backtest_worker` 后台轮询（`POLL_INTERVAL=3s`，`TIMEOUT=300s`）
- `core/backtest/jqcli_auth.py` — 聚宽登录态解析（token/cookie/api_base），`JqcliNotConfiguredError`
- `core/backtest/registry.py` — `BacktestRegistry` 内存索引

**RAG**
- `core/jq_kb/retrievers.py` — 三库 hybrid 检索器（`JqApiRetriever` / `JqDictRetriever` / `JqStrategyRetriever`），共享同一管线
- `core/jq_kb/ingest.py` / `chunkers/` / `parser/` — 数据入库与切分
- `core/jq_kb/embeddings.py` — embedding 走 HTTP 远程 API；reranker 走本地 `SentenceTransformerRerank`（或远程 `RerankPostprocessor` 备选）
- `core/jq_kb/embedding_client.py` — HTTP `/embeddings` 客户端（OpenAI-compatible）

**扩展**
- `skills/storage/local_skill_storage.py` — 磁盘 SKILL.md 协议（`public/` + `custom/`），路径穿越校验
- `config/extensions_config.py` — `extensions_config.json` 运行时可切换状态（skills / MCP servers / interceptors）
- `core/chat/subagents/executor.py` — 子代理在独立 asyncio loop 执行，`checkpointer=False` 隔离状态

**数据持久化**
- `db/session.py` — async SQLAlchemy engine + session factory（pool 10 + overflow 20）
- `db/models/` — `user` / `thread` / `run` / `memory`
- `app_context/app_context.py` — `AppContext` frozen 容器，持有 session_factory / checkpointer / run_manager / mcp_tools 等

## 3. 数据流

### 3.1 对话一轮（chat turn）

```
Frontend POST /api/v1/threads/{id}/runs/stream  (经 Next.js route 代理)
  → AuthMiddleware 校验 JWT
  → thread/views.py: start_run() 将 input 注入 RunManager
  → sse_consumer(): run_agent() 调 graph.astream(stream_modes=["values","messages","custom"])
    → agent_node:
        before_model: 21 级 middleware 链依次执行
          (sanitization → dynamic context → jq prefetch → skill activation → ...)
        model call: ChatOpenAI(streaming)
        after_model: (token usage / title / memory / loop detection / ...)
      conditional edge: 有 tool_calls → tool_node → 回 agent_node；无 → END
    → 每个 chunk 经 get_stream_writer() → SSE bridge
    → Next.js route: fetch backend → ReadableStream.getReader() 透传 → Frontend 手动解析 SSE
```

- run 级并发控制由 `RunManager.create_or_reject`（默认 `reject`：同 thread 已有 inflight run 抛 `ConflictError`；可选 `interrupt`/`rollback`）
- 断连行为由 `DisconnectMode` 决定（cancel / continue）
- `AppContext.stream_bridge`（生产用 Memory bridge）跨请求转发事件

### 3.2 回测

```
Frontend POST /api/v1/backtest  (策略代码 + BacktestParams)
  → backtest/views.py: _start_backtest_worker()
  → BacktestService.submit(): create_strategy → run_backtest (jqcli)
  → 返回 backtest_id；_worker_tasks[backtest_id] 后台轮询
  → 轮询 DONE/FAILED → 写 BacktestRegistry
Frontend GET /api/v1/backtest/{id}/stream  (EventSource)
  → backtest_sse_consumer: 从 registry 读取结果 + logs + trades + holdings → SSE 推送
```

- jqcli 登录态：`resolve_jqcli_credentials` 从环境变量/配置解析 token+cookie，未配置抛 `JqcliNotConfiguredError`
- worker 超时 300s，轮询间隔 3s

### 3.3 RAG 检索（agent 主动调用 tool）

```
agent 调 search_jq_api(query, function_name="")
  → JqApiRetriever.retrieve()
    ├─ retrieve_by_function_name()   ← metadata 精确匹配短路
    └─ _retrieve_hybrid()
         ├─ QueryFusionRetriever: LLM 生成 N 变体查询
         ├─ VectorIndexRetriever (Chroma) + BM25Retriever (pickle)
         ├─ RRF 融合 (reciprocal_rerank)
         └─ get_reranker(): 本地 BGE-reranker-large cross-encoder 重排 (无本地模型则跳过)
  → 返回 top-k 文档片段 (format_api_hits)
```

- 默认 `backtest_env` 过滤，排除 research-only / live-only API（♠ 标记）
- jq_dict / jq_strategy 检索器结构同上；jq_strategy 支持 `post_id` 精确匹配短路 + year/strategy_type 元数据过滤

## 4. 数据层

| 存储 | 用途 | 位置 | 状态 |
|------|------|------|------|
| SQLite (aiosqlite) | user/thread/run/memory 持久化 | `data.db` | 默认 |
| SQLite (aiosqlite) | LangGraph checkpointer | `checkpoints.db` | 默认 `checkpointer_backend=sqlite` |
| ChromaDB | jq_api/jq_dict/jq_strategy 向量索引 | `backend/data/jq_*/chroma_db` | 已生成 |
| BM25 pickle | 稀疏检索节点（与向量 RRF 融合） | `backend/data/jq_*/bm25.pkl` | jq_api/jq_dict 已生成；jq_strategy 未生成 |
| 远程 Embedding API | 文本向量化 | `{jq_kb_embedding_base_url}/embeddings` | HTTP |
| 本地 Reranker | cross-encoder 重排 | `backend/data/models/BAAI/bge-reranker-large` | 本地 HF；远程备选 `RerankPostprocessor` |
| Kùzu | jq_strategy 策略图谱 | — | **计划中，未实现**（见 `docs/jq_kb/PLAN.md`） |

## 5. Middleware 链

`build_middlewares()` 按 `RuntimeFeatures` 条件装配。顺序固定，依赖前序 middleware 的产物（如 DynamicContext 先于 JqPrefetch）。

| # | Middleware | 阶段 | 作用 |
|---|-----------|------|------|
| 1 | LLMErrorHandling | before/after model | 传输错误熔断 |
| 2 | InputSanitization | before model | prompt 注入防御 |
| 3 | DanglingToolCall | before model | 修补无 ToolMessage 的 AIMessage(tool_calls) |
| 4 | SystemMessageCoalescing | before model | 合并相邻 SystemMessage |
| 5 | ToolErrorHandling | wrap_tool_call (outer) | tool 异常 → error ToolMessage |
| 6 | ToolOutputBudget | wrap_tool_call (inner) | 超大 ToolMessage 落盘 + head/tail 摘要 |
| 7 | DynamicContext | before model | 注入 `<system-reminder>` 日期 / memory HumanMessage |
| 8 | JqPrefetch | before model | 扫描 `__user` 消息，metadata 精确匹配预取 jq 文档 → `__jqref` |
| 9 | SkillActivation | before model | `/<skill>` 斜杠注入 |
| 10 | Todo | before model | plan-mode 任务跟踪 |
| 11 | Summarization | after model | 触发 memory flush 事件 |
| 12 | TokenUsage | after model | 累计 prompt/completion token |
| 13 | Title | after model | turn 1 后设置 thread 标题 |
| 14 | Memory | after model | evolution 写回（条件） |
| 15 | DeferredToolFilter | before model | 隐藏 deferred MCP 工具（条件） |
| 16 | SubagentLimit | before model | 并发子代理上限（条件） |
| 17 | LoopDetection | before/after model | 检测重复 tool-call 循环 |
| 18 | TokenBudget | before/after model | token 超限警告 / 硬停 |
| 19 | *(custom)* | — | 外部注入点 |
| 20 | SafetyFinishReason | after model | safety 终止时剥离 tool_calls |
| 21 | Clarification | after model | `ask_clarification` 终端中断 |

- `wrap_tool_call` 钩子（5/6）在 ToolNode 边界形成栈，相对顺序（error outer, budget inner）才是关键，链中位置仅为可读性
- 条件 middleware 缺失时链缩短，编号非连续

## 6. 配置分层

| 层 | 位置 | 内容 | 变更时机 |
|----|------|------|---------|
| 启动 | `app/settings.py` (`.env`) | model / DB URL / JWT / 路径 / checkpointer | 部署 |
| 运行时 | `extensions_config.json` | skills 开关 / MCP servers / interceptors | 运维热切换 |
| 内存 | `RuntimeFeatures` (per-run) | model_name / thinking / plan_mode / subagent | 每轮对话可注入 |

`RuntimeFeatures` 经 `config["configurable"]` 注入，`_CONTEXT_KEYS` 白名单：`model_name` / `thinking_enabled` / `reasoning_effort` / `is_plan_mode` / `subagent_enabled`。
