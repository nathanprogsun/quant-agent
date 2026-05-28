# quant-agent 复刻 deer-flow L1+L2 功能设计方案

> 日期: 2026-05-28
> 状态: Draft
> 策略: 参考实现 (非直接移植)

---

## 一、背景与目标

### 1.1 现状

quant-agent 基于 deer-flow 的核心架构进行了精简实现，但在以下方面存在差距：

| 维度 | quant-agent | deer-flow | 完成度 |
|------|------------|----------|--------|
| 核心架构 | StreamBridge, RunManager, SSE | 同上 | 70% |
| Agent执行 | 基础StateGraph | 完整中间件链 | 50% |
| 前端UI | 4个组件 | 60+组件 | 15% |
| 记忆系统 | **无** | 完整API+自动更新 | 0% |
| Skills系统 | **无** | Markdown-based工作流 | 0% |
| 工具生态 | **无** | MCP+内置工具 | 0% |
| 认证安全 | 基础JWT | RBAC+速率限制 | 40% |

### 1.2 目标

在 **2-4周冲刺模式** 下，采用 **参考实现** 策略，于quant-agent现有架构内重新实现deer-flow的L1核心业务和L2企业功能。

**成功标准：**
- [ ] 前端：完整的消息渲染、代码高亮、Token统计、模型选择
- [ ] Agent：11层中间件全部启用并正常工作
- [ ] 记忆：UserContext存储 + LLM自动更新 + API端点
- [ ] Skills：Markdown格式技能定义 + 注册 + 执行
- [ ] 安全：RBAC权限 + 登录速率限制 + Token版本控制
- [ ] 工具：MCP工具集成 + 内置工具(task/bash/search)
- [ ] **端到端可运行**

### 1.3 约束

- **部署环境**: 本地开发，SQLite存储
- **架构一致性**: 遵循quant-agent现有DDD架构，不引入新目录层级
- **代码质量**: 无单元测试、无集成测试，专注功能实现
- **策略**: 参考deer-flow设计重新实现，非直接移植代码

---

## 二、架构设计

### 2.1 整体架构

```
┌─────────────────────────────────────────────────────────────────┐
│  Frontend (Next.js)                                              │
│  ├── 60+ 组件 (从deer-flow复制，适配shadcn样式)                  │
│  ├── CSRF保护 + Token追踪                                        │
│  └── useThreadStream 增强版                                      │
├─────────────────────────────────────────────────────────────────┤
│  Backend (FastAPI)                                               │
│                                                                  │
│  ┌─ web/ (Gateway层 - 统一入口) ─────────────────────────────┐  │
│  │  ├── api/threads/      # Thread CRUD                       │  │
│  │  ├── api/chat/         # Run执行 + SSE                     │  │
│  │  ├── api/memory/       # Memory API (新增)                 │  │
│  │  ├── api/skills/       # Skills API (新增)                 │  │
│  │  └── middleware/auth_middleware.py  # 认证中间件           │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌─ core/chat/ (Harness层 - 业务逻辑) ───────────────────────┐  │
│  │  ├── agent/            # Agent工厂 (现有)                   │  │
│  │  ├── middlewares/      # 中间件链 (现有，需启用)            │  │
│  │  ├── memory/           # 记忆系统 (新增)                    │  │
│  │  ├── skills/           # 技能系统 (新增)                    │  │
│  │  ├── tools/            # 工具系统 (新增)                    │  │
│  │  └── service/          # 核心服务 (现有)                   │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌─ common/ (基础设施) ──────────────────────────────────────┐  │
│  │  ├── stream_bridge/    # SSE事件桥 (现有)                  │  │
│  │  └── runs/            # Run生命周期 (现有)                 │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌─ db/ (数据层) ────────────────────────────────────────────┐  │
│  │  ├── models/          # ORM模型                           │  │
│  │  └── dao/             # 数据访问对象                       │  │
│  └────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 模块依赖关系

```
web/api/
    │
    ├── threads/ ──────────▶ core/chat/service/thread_service.py
    │                         └── db/dao/thread_repository.py
    │
    ├── chat/ ─────────────▶ core/chat/agent/lead_agent.py
    │                         ├── core/chat/middlewares/ (启用链)
    │                         ├── core/chat/memory/middleware.py
    │                         ├── core/chat/skills/executor.py
    │                         └── common/stream_bridge/
    │
    ├── memory/ (新增) ────▶ core/chat/memory/service.py
    │                         └── db/models/memory.py (新增)
    │
    └── skills/ (新增) ────▶ core/chat/skills/registry.py
                              └── core/chat/skills/executor.py
```

### 2.3 quant-agent 与 deer-flow 目录映射

| deer-flow | quant-agent | 说明 |
|-----------|-------------|------|
| `gateway/` | `web/` | 网关层 |
| `harness/deerflow/agents/` | `core/chat/` | 业务层 |
| `harness/deerflow/memory/` | `core/chat/memory/` | 记忆系统 |
| `harness/deerflow/skills/` | `core/chat/skills/` | 技能系统 |
| `harness/deerflow/tools/` | `core/chat/tools/` | 工具系统 |
| `harness/deerflow/runtime/` | `common/` | 基础设施 |

---

## 三、功能模块设计

### 3.1 前端增强 (Week 1)

#### 3.1.1 需要复制的前端组件

| 来源 (deer-flow) | 目标 (quant-agent) | 说明 |
|-----------------|-------------------|------|
| `components/ai-elements/message.tsx` | `components/workspace/Message.tsx` | 消息渲染 |
| `components/ai-elements/prompt-input.tsx` | `components/workspace/InputBox.tsx` | 输入框 |
| `components/ai-elements/code-block.tsx` | `components/workspace/CodeBlock.tsx` | 代码高亮 |
| `components/ai-elements/artifact.tsx` | `components/workspace/Artifact.tsx` | 代码片段 |
| `components/ai-elements/reasoning.tsx` | `components/workspace/Reasoning.tsx` | 思考过程 |
| `components/ai-elements/token-usage.tsx` | `components/workspace/TokenUsage.tsx` | Token统计 |
| `components/ai-elements/model-selector.tsx` | `components/workspace/ModelSelector.tsx` | 模型选择 |
| `components/workspace/command-palette.tsx` | `components/workspace/CommandPalette.tsx` | 命令面板 |
| `core/api/fetcher.ts` | `core/api/client.ts` | API客户端 |
| `core/i18n/` | `core/i18n/` | 国际化 |

#### 3.1.2 API客户端增强

```typescript
// core/api/client.ts 新增功能

// 1. CSRF保护
function injectCsrfHeader(url: URL, init: RequestInit): RequestInit {
  const csrfToken = document.cookie.match(/csrf_token=([^;]+)/)?.[1];
  if (csrfToken && !["GET", "HEAD", "OPTIONS"].includes(init.method || "GET")) {
    init.headers = { ...init.headers, "X-CSRF-Token": csrfToken };
  }
  return init;
}

// 2. Token使用追踪
interface TokenUsage {
  inputTokens: number;
  outputTokens: number;
  totalTokens: number;
}

// 3. Stream模式支持
const streamModes = ["values", "messages", "updates", "checkpoints"];
```

#### 3.1.3 useThreadStream 增强

```typescript
// core/threads/useThreadStream.ts 新增

interface UseThreadStreamOptions {
  // 现有...
  onTokenUsage?: (usage: TokenUsage) => void;
  onReasoning?: (reasoning: string) => void;
  onCustomEvent?: (event: string, data: any) => void;
  onUpdateEvent?: (data: any) => void;
}
```

### 3.2 中间件链 (Week 2)

#### 3.2.1 中间件列表

| 中间件 | 优先级 | 说明 |
|--------|--------|------|
| DynamicContextMiddleware | P0 | 注入当前日期、用户上下文 |
| TitleMiddleware | P0 | 首轮对话后生成标题 |
| TokenUsageMiddleware | P0 | 记录Token消耗 |
| SummarizationMiddleware | P1 | Token超限时压缩上下文 |
| MemoryMiddleware | P1 | 注入用户记忆到Prompt |
| LoopDetectionMiddleware | P2 | 检测重复模式并打断 |
| ClarificationMiddleware | P2 | 拦截需要澄清的请求 |
| SubagentLimitMiddleware | P2 | 限制Subagent并发数 |
| DeferredToolFilterMiddleware | P3 | 延迟工具加载 |
| ViewImageMiddleware | P3 | 注入图片到上下文 |
| SafetyFinishReasonMiddleware | P3 | 安全终止检查 |

#### 3.2.2 中间件基类

```python
# core/chat/middlewares/base.py (现有，需确认完整性)

class AgentMiddleware(ABC):
    """Agent中间件基类 - 四个钩子时机"""

    async def before_model(self, state: dict, config: dict) -> dict | None:
        """LLM调用前"""
        return None

    async def after_model(self, state: dict, config: dict) -> dict | None:
        """LLM调用后"""
        return None

    async def before_tool(self, tool_name: str, tool_input: dict, config: dict) -> dict | None:
        """工具调用前"""
        return None

    async def after_tool(self, tool_name: str, tool_input: dict, result: Any, config: dict) -> Any | None:
        """工具调用后"""
        return None
```

#### 3.2.3 需要新增的中间件

**DynamicContextMiddleware:**
```python
# core/chat/middlewares/dynamic_context_middleware.py

class DynamicContextMiddleware(AgentMiddleware):
    """注入动态上下文到系统Prompt"""

    async def before_model(self, state: dict, config: dict) -> dict | None:
        # 注入当前日期、时间、用户偏好等
        current_date = datetime.now().strftime("%Y年%m月%d日 %H:%M")
        return {"context": {"current_date": current_date}}
```

**MemoryMiddleware:**
```python
# core/chat/middlewares/memory_middleware.py

class MemoryMiddleware(AgentMiddleware):
    """从记忆系统注入用户上下文"""

    async def before_model(self, state: dict, config: dict) -> dict | None:
        user_id = config.get("user_id")
        if not user_id:
            return None
        memory = await self.memory_service.get_user_memory(user_id)
        return {"memory_context": memory.to_prompt_string()}
```

### 3.3 记忆系统 (Week 3)

#### 3.3.1 数据模型

```python
# db/models/memory.py

from sqlalchemy import Column, String, Text, Float, DateTime, ForeignKey
from app.db.models.base import BaseModel

class UserMemory(BaseModel):
    """用户记忆"""
    __tablename__ = "user_memories"

    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    memory_type = Column(String)  # work_context, personal_context, fact
    content = Column(Text)
    confidence = Column(Float, default=1.0)
    source = Column(String)  # 对话来源
    created_at = Column(DateTime)
    updated_at = Column(DateTime)

class MemoryFact(BaseModel):
    """事实卡片"""
    __tablename__ = "memory_facts"

    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    fact_type = Column(String)  # preference, knowledge, relationship
    content = Column(Text)
    embedding = Column(Text)  # 可选，用于未来RAG
    created_at = Column(DateTime)
```

#### 3.3.2 API端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/memory` | GET | 获取用户记忆 |
| `/api/memory` | DELETE | 删除用户记忆 |
| `/api/memory/facts` | GET | 获取事实列表 |
| `/api/memory/facts` | POST | 创建事实 |
| `/api/memory/facts/{id}` | PATCH | 更新事实 |
| `/api/memory/facts/{id}` | DELETE | 删除事实 |
| `/api/memory/reload` | POST | 重新加载记忆 |

#### 3.3.3 记忆服务

```python
# core/chat/memory/service.py

@dataclass
class UserMemoryContext:
    """注入到Prompt的用户上下文"""
    work_context: str | None
    personal_context: str | None
    recent_history: str | None
    facts: list[str]

    def to_prompt_string(self) -> str:
        """转换为Prompt字符串"""
        parts = []
        if self.work_context:
            parts.append(f"<工作上下文>\n{self.work_context}\n</工作上下文>")
        if self.personal_context:
            parts.append(f"<个人上下文>\n{self.personal_context}\n</个人上下文>")
        if self.facts:
            parts.append(f"<已知事实>\n" + "\n".join(f"- {f}" for f in self.facts) + "\n</已知事实>")
        return "\n".join(parts)

class MemoryService:
    """记忆服务"""

    async def get_user_memory(self, user_id: str) -> UserMemoryContext:
        """获取用户记忆上下文"""

    async def update_from_conversation(self, user_id: str, messages: list[BaseMessage]) -> None:
        """从对话中提取并更新记忆 (LLM驱动)"""

    async def extract_facts(self, messages: list[BaseMessage]) -> list[str]:
        """使用LLM从对话中提取事实"""
```

### 3.4 Skills系统 (Week 3)

#### 3.4.1 技能定义格式

```markdown
# skill_stock_analysis

## Metadata
name: stock_analysis
description: 分析股票基本面和技术面
version: 1.0.0

## System Prompt
你是一个专业的股票分析师。请对 {symbol} 进行全面分析...

## Tools
- get_stock_price
- get_financial_data
- search_web

## Parameters
{
  "type": "object",
  "properties": {
    "symbol": {"type": "string", "description": "股票代码"}
  },
  "required": ["symbol"]
}

## Max Iterations
10
```

#### 3.4.2 技能注册

```python
# core/chat/skills/registry.py

@dataclass(frozen=True)
class SkillDefinition:
    name: str
    description: str
    version: str
    parameters: dict
    prompt_template: str
    tools: list[str]
    max_iterations: int = 10

class SkillRegistry:
    """技能注册中心"""

    def __init__(self):
        self._skills: dict[str, SkillDefinition] = {}

    def register(self, skill: SkillDefinition) -> None:
        self._skills[skill.name] = skill

    def get(self, name: str) -> SkillDefinition | None:
        return self._skills.get(name)

    def list_all(self) -> list[SkillDefinition]:
        return list(self._skills.values())

    def to_tools(self) -> list[BaseTool]:
        """转换为LangChain Tool"""
        ...
```

#### 3.4.3 技能执行器

```python
# core/chat/skills/executor.py

class SkillExecutor:
    """将Skill编译为LangGraph子图"""

    def build_skill_graph(self, skill: SkillDefinition, config: RunnableConfig) -> CompiledStateGraph:
        """构建技能子图"""
        ...

    async def execute(self, skill_name: str, input_text: str, config: RunnableConfig) -> str:
        """执行技能并返回结果"""
        skill = self.registry.get(skill_name)
        graph = self.build_skill_graph(skill, config)
        result = await graph.ainvoke({"messages": [HumanMessage(content=input_text)]})
        return result["messages"][-1].content
```

### 3.5 工具系统 (Week 4)

#### 3.5.1 内置工具

| 工具 | 说明 | 优先级 |
|------|------|--------|
| task_tool | Subagent任务委托 | P0 |
| bash | 命令执行 | P1 |
| python_repl | Python代码执行 | P1 |
| search | 网络搜索 | P2 |
| crawl | 网页抓取 | P2 |

#### 3.5.2 MCP集成

```python
# core/chat/tools/mcp/client.py

class MCPClient:
    """MCP工具客户端"""

    async def get_tools(self, servers: list[str]) -> list[BaseTool]:
        """从MCP服务器获取工具"""
        ...

    async def execute_tool(self, tool_name: str, arguments: dict) -> str:
        """执行MCP工具"""
        ...
```

### 3.6 企业安全功能 (Week 4)

#### 3.6.1 权限系统

```python
# core/chat/authz.py

PERMISSIONS = {
    "threads:read": ["get_thread", "list_threads", "get_thread_history"],
    "threads:write": ["create_thread", "update_thread", "update_thread_title"],
    "threads:delete": ["delete_thread"],
    "runs:create": ["create_run", "stream_run", "wait_run"],
    "runs:read": ["get_run", "list_runs", "get_run_messages"],
    "runs:cancel": ["cancel_run"],
    "memory:read": ["get_memory", "list_facts"],
    "memory:write": ["create_fact", "update_fact", "delete_fact"],
    "skills:read": ["list_skills", "get_skill"],
    "skills:write": ["create_skill", "update_skill", "delete_skill"],
}

def require_permission(resource: str, action: str, owner_check: bool = False):
    """权限装饰器"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            user = request.state.current_user
            if not user:
                raise HTTPException(401, "Unauthorized")

            required_perm = f"{resource}:{action}"
            if required_perm not in PERMISSIONS.get(user.role, []):
                raise HTTPException(403, "Forbidden")

            # 所有者检查
            if owner_check:
                resource_id = kwargs.get("thread_id") or kwargs.get("run_id")
                if not await check_resource_ownership(user.id, resource_id):
                    raise HTTPException(403, "Not resource owner")

            return await func(*args, **kwargs)
        return wrapper
    return decorator
```

#### 3.6.2 登录速率限制

```python
# web/middleware/rate_limit_middleware.py

class LoginRateLimiter:
    """登录速率限制器"""

    MAX_ATTEMPTS = 5
    LOCKOUT_SECONDS = 300
    _attempts: dict[str, tuple[int, float]] = {}  # ip -> (count, first_attempt)

    @classmethod
    def check(cls, ip: str) -> bool:
        """检查是否允许登录"""
        if ip not in cls._attempts:
            return True

        count, first_attempt = cls._attempts[ip]
        if time.time() - first_attempt > cls.LOCKOUT_SECONDS:
            del cls._attempts[ip]
            return True

        return count < cls.MAX_ATTEMPTS

    @classmethod
    def record_failure(cls, ip: str) -> None:
        """记录失败尝试"""
        if ip not in cls._attempts:
            cls._attempts[ip] = (0, time.time())
        cls._attempts[ip] = (cls._attempts[ip][0] + 1, cls._attempts[ip][1])

    @classmethod
    def reset(cls, ip: str) -> None:
        """重置"""
        cls._attempts.pop(ip, None)
```

#### 3.6.3 Token版本控制

```python
# db/models/user.py 新增字段

class User(BaseModel):
    # ... 现有字段 ...
    token_version = Column(Integer, default=1)

# auth/service.py 修改

async def create_access_token(user: User) -> str:
    """创建访问令牌，包含token_version"""
    payload = {
        "sub": str(user.id),
        "token_version": user.token_version,
        "exp": datetime.utcnow() + timedelta(days=7)
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm="HS256")

async def verify_token(token: str) -> User:
    """验证令牌，检查token_version"""
    payload = jwt.decode(token, settings.jwt_secret_key, algorithms=["HS256"])
    user_id = payload.get("sub")
    token_version = payload.get("token_version")

    user = await user_service.find_by_id(user_id)
    if not user or user.token_version != token_version:
        raise HTTPException(401, "Token expired")

    return user

# 修改密码时递增版本
async def update_password(user_id: str, new_password: str) -> None:
    user = await user_service.find_by_id(user_id)
    user.token_version += 1
    user.hashed_password = await hash_password(new_password)
    await user_service.save(user)
```

---

## 四、API端点汇总

### 4.1 现有端点 (保持不变)

```
GET    /api/threads                     # 列出线程
POST   /api/threads                     # 创建线程
GET    /api/threads/{thread_id}        # 获取线程
PATCH  /api/threads/{thread_id}        # 更新线程
DELETE /api/threads/{thread_id}        # 删除线程
GET    /api/threads/{thread_id}/history # 获取历史
POST   /api/threads/{thread_id}/runs/stream # SSE流式
POST   /api/threads/{thread_id}/runs/{run_id}/cancel # 取消
```

### 4.2 新增端点

#### Memory API
```
GET    /api/memory                      # 获取用户记忆
DELETE /api/memory                      # 删除用户记忆
GET    /api/memory/facts                # 获取事实列表
POST   /api/memory/facts                # 创建事实
PATCH  /api/memory/facts/{fact_id}     # 更新事实
DELETE /api/memory/facts/{fact_id}     # 删除事实
POST   /api/memory/reload               # 重新加载
```

#### Skills API
```
GET    /api/skills                      # 列出技能
GET    /api/skills/{skill_name}         # 获取技能详情
POST   /api/skills                      # 创建技能
PUT    /api/skills/{skill_name}         # 更新技能
DELETE /api/skills/{skill_name}         # 删除技能
```

#### Auth增强
```
POST   /api/v1/auth/change-password     # 修改密码
POST   /api/v1/auth/logout              # 登出
```

---

## 四、任务依赖图与Worktree策略

### 4.1 任务依赖图

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           任务依赖图 (修正版)                            │
│                                                                         │
│  T1: 前端基础 (wt-frontend) - 无依赖，可独立启动                        │
│   ├── CSRF保护                                                          │
│   ├── API client增强                                                     │
│   └── 组件复制 (Message, InputBox, CodeBlock, Artifact, Reasoning)       │
│                                                                         │
│  T2: 中间件链 (wt-middleware) - 无依赖，可独立启动                       │
│   ├── 中间件基类 (base.py)                                              │
│   ├── DynamicContextMiddleware                                          │
│   ├── TitleMiddleware (已有代码，待启用)                                │
│   ├── TokenUsageMiddleware (已有代码，待启用)                            │
│   ├── SummarizationMiddleware (已有代码，待启用)                        │
│   ├── ClarificationMiddleware                                           │
│   ├── LoopDetectionMiddleware                                           │
│   └── SubagentLimitMiddleware                                          │
│                                                                         │
│  T3: 记忆系统 (wt-memory) - 依赖T2中间件基类                            │
│   ├── db/models/memory.py                                              │
│   ├── memory/service.py                                                │
│   ├── memory/api.py                                                    │
│   └── MemoryMiddleware ───────────────────────────────────────────┐   │
│       (依赖MemoryService必须在T3中先完成)                          │   │
│                                                                   │   │
│  T6: 企业安全 (wt-security) - 无依赖，可独立启动                      │   │
│   ├── RBAC权限装饰器                                                 │   │
│   ├── 登录速率限制                                                   │   │
│   └── Token版本控制                                                  │   │
│                                                                   │   │
│  T5: 工具系统 (wt-tools) - 依赖T2中间件基类                          │   │
│   ├── tools/builtin/task_tool.py                                     │   │
│   ├── tools/builtin/bash_tool.py                                     │   │
│   └── tools/mcp/client.py                                           │   │
│                                                                   │   │
│  T4: Skills系统 (wt-skills) - 依赖T3(记忆上下文)和T5(工具执行) ──▶┘   │
│   ├── skills/registry.py                                              │
│   ├── skills/executor.py                                              │
│   ├── skills/storage.py                                               │
│   └── skills/api.py                                                   │
│                                                                         │
│  T7: 端到端集成 (wt-integration) - 依赖T1-T6全部                       │
│   └── 完整流程可运行验证                                               │
└─────────────────────────────────────────────────────────────────────────┘
```

### 4.2 Worktree与并发分组

| Worktree | 任务 | 依赖 | 启动顺序 | 测试方式 |
|----------|------|------|---------|---------|
| `wt-frontend` | T1: 前端增强 | 无 | 1 | E2E + 单元 |
| `wt-middleware` | T2: 中间件链 | 无 | 1 | E2E + 单元 |
| `wt-security` | T6: 企业安全 | 无 | 1 | E2E + 单元 |
| `wt-memory` | T3: 记忆系统 | T2基类 | 2 | E2E + 单元 |
| `wt-tools` | T5: 工具系统 | T2基类 | 2 | E2E + 单元 |
| `wt-skills` | T4: Skills系统 | T3+T5 | 3 | E2E + 单元 |
| `wt-integration` | T7: E2E测试 | T1-T6 | 4 | E2E |

### 4.3 依赖关系说明

**关键修正: MemoryMiddleware 依赖 MemoryService**

`MemoryMiddleware` 在 before_model 钩子中调用 `MemoryService.get_user_memory()`，因此：
- **T3必须在T2之前完成MemoryService部分**
- T2中的MemoryMiddleware需要等T3的MemoryService就绪后才能完整工作

**修正后的启动顺序:**

```
第一批 (并行启动):
├── wt-frontend    (T1: 前端)
├── wt-middleware  (T2: 中间件 - 但MemoryMiddleware部分需等T3)
└── wt-security    (T6: 企业安全)

第二批 (等T2 T3完成后启动):
└── wt-memory      (T3: 记忆系统 - MemoryService完成后T2的MemoryMiddleware才能工作)

第三批 (等T3, T5完成后启动):
├── wt-tools       (T5: 工具系统 - 依赖T2基类)
└── wt-skills      (T4: Skills系统 - 依赖T3记忆上下文和T5工具)

第四批 (等全部完成后):
└── wt-integration (T7: E2E测试)
```

### 4.4 合并流程

```
每个worktree完成 → PR到main → 合并后本地:
git checkout main && git pull origin main
删除本地worktree分支
```

### 4.5 测试策略

| 测试类型 | 适用范围 | 说明 |
|---------|---------|------|
| **E2E测试** | 所有功能模块 | Playwright端到端测试，验证真实功能 |
| **单元测试** | 核心逻辑 | 如记忆提取、权限检查、速率限制逻辑 |
| **集成测试** | API端点 | FastAPI TestClient 测试REST API |

### 4.6 交付标准

每个任务完成后必须满足:
1. **代码完成**: 实现文档中定义的所有功能
2. **测试通过**: E2E + 单元测试全部通过
3. **可运行**: 启动后端/前端服务，功能正常可用
4. **合并条件**: PR review通过，CI green，main分支最新

---

## 六、风险与缓解

| 风险 | 影响 | 缓解 |
|------|------|------|
| 时间不足 | 可能无法完成全部模块 | 优先级排序，L3渠道功能可延后 |
| 中间件冲突 | 多个中间件可能相互干扰 | 逐个启用，逐步测试 |
| 前端适配 | 组件复制后样式可能不统一 | 使用shadcn作为基础，统一样式 |
| LLM调用成本 | 记忆更新等会产生额外LLM调用 | 使用便宜模型(gpt-4o-mini) |
| T2/T3循环依赖 | MemoryMiddleware依赖MemoryService | T3先完成MemoryService，T2再启用MemoryMiddleware |

---

## 七、文件清单

### 新增文件

```
backend/app/
├── core/chat/
│   ├── middlewares/
│   │   ├── dynamic_context_middleware.py  # 新增
│   │   ├── memory_middleware.py           # 新增
│   │   ├── clarification_middleware.py    # 新增
│   │   ├── loop_detection_middleware.py   # 新增
│   │   ├── subagent_limit_middleware.py   # 新增
│   │   └── deferred_tool_filter_middleware.py  # 新增
│   ├── memory/
│   │   ├── __init__.py
│   │   ├── api.py                         # 新增 - Memory API端点
│   │   ├── service.py                     # 新增 - 记忆服务
│   │   ├── models.py                      # 新增 - 数据模型
│   │   └── middleware.py                  # 新增 - MemoryMiddleware
│   ├── skills/
│   │   ├── __init__.py
│   │   ├── registry.py                    # 新增
│   │   ├── executor.py                    # 新增
│   │   ├── storage.py                     # 新增
│   │   └── models.py                      # 新增
│   └── tools/
│       ├── __init__.py
│       ├── builtin/                       # 新增目录
│       │   ├── task_tool.py
│       │   ├── bash_tool.py
│       │   └── search_tool.py
│       └── mcp/
│           ├── __init__.py
│           └── client.py                  # 新增
├── web/
│   └── api/
│       ├── memory/                        # 新增目录
│       │   └── route.py
│       └── skills/                        # 新增目录
│           └── route.py
└── db/
    └── models/
        └── memory.py                      # 新增 - ORM模型

frontend/src/
├── components/
│   └── workspace/
│       ├── Message.tsx                    # 复制
│       ├── InputBox.tsx                   # 复制
│       ├── CodeBlock.tsx                  # 复制
│       ├── Artifact.tsx                   # 复制
│       ├── Reasoning.tsx                  # 复制
│       ├── TokenUsage.tsx                 # 复制
│       ├── ModelSelector.tsx               # 复制
│       └── CommandPalette.tsx             # 复制
└── core/
    ├── api/
    │   └── client.ts                      # 增强
    └── i18n/                              # 复制
```

### 修改文件

```
backend/app/
├── core/chat/agent/lead_agent.py         # 启用中间件链
├── core/chat/middlewares/base.py          # 确认完整性
├── core/chat/middlewares/title_middleware.py  # 确认启用
├── core/chat/middlewares/token_usage_middleware.py  # 确认启用
├── core/chat/middlewares/summarization_middleware.py  # 确认启用
├── db/models/user.py                      # 添加token_version
├── web/api/chat/views.py                  # 添加权限装饰器
└── web/middleware/rate_limit_middleware.py # 新增

frontend/src/
├── core/api.ts                            # 增强CSRF
└── core/threads/api.ts                    # 增强useThreadStream
```
