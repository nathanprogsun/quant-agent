# Claude Code Multi-Subagent E2E Configuration

## Overview

本目录定义了 Claude Code 多 Subagent 并行 E2E 测试的配置文件。

## Agent 定义

### 1. orchestrator (主编排器)

**角色**: 任务协调者
**职责**:
- 解析测试需求
- 并行调度 subagent
- 汇总测试结果
- 管理 bug reports

**启动命令**:
```bash
npx tsx tests/e2e/multi-agent/orchestrator.ts
```

### 2. auth-e2e-agent

**角色**: Auth 流程测试专家
**测试域**: auth.spec.ts
**职责**:
- 登录功能测试
- 注册功能测试
- 认证失败处理
- 路由守卫验证

**运行命令**:
```bash
npx playwright test tests/e2e/auth.spec.ts --reporter=list
```

### 3. chat-e2e-agent

**角色**: Chat 对话测试专家
**测试域**: chat.spec.ts
**职责**:
- 消息发送测试
- SSE 流式响应测试
- 工具调用渲染
- 乐观更新验证

**运行命令**:
```bash
npx playwright test tests/e2e/chat.spec.ts --reporter=list
```

### 4. workspace-e2e-agent

**角色**: Workspace UI 测试专家
**测试域**: threads.spec.ts, reconnect.spec.ts
**职责**:
- 线程列表加载
- 线程切换
- 重连机制
- UI 状态管理

**运行命令**:
```bash
npx playwright test tests/e2e/threads.spec.ts tests/e2e/reconnect.spec.ts --reporter=list
```

## Claude Code Subagent 启动方式

### 方式 1: 使用 Agent Tool (推荐)

```typescript
// 在 Claude Code 中启动多个并行 agent
Agent({
  description: "Auth E2E Testing Agent",
  prompt: "运行 auth.spec.ts E2E 测试并汇报结果",
  subagent_type: "ecc:e2e"
})

Agent({
  description: "Chat E2E Testing Agent",
  prompt: "运行 chat.spec.ts E2E 测试并汇报结果",
  subagent_type: "ecc:e2e"
})

Agent({
  description: "Workspace E2E Testing Agent",
  prompt: "运行 threads.spec.ts 和 reconnect.spec.ts E2E 测试并汇报结果",
  subagent_type: "ecc:e2e"
})
```

### 方式 2: 使用 Claude Code CLI

```bash
# 启动编排器
/claude-code -p "运行 E2E 多 agent 测试"

# 或指定特定 agent
/claude-code -p "启动 auth-e2e-agent 运行 auth.spec.ts"
```

## 并行执行流程

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Claude Code Main Session                       │
│                                                                       │
│  1. User: "运行完整的 E2E 测试"                                        │
│                                                                       │
│  2. Main Agent 调用 Skill: ecc:e2e                                   │
│                                                                       │
│  3. Main Agent 并行启动 3 个 Subagents:                              │
│     ┌─────────────────────────────────────────────────────────────┐  │
│     │ Agent 1: auth-e2e-agent                                     │  │
│     │   - 连接到 Playwright browser                               │  │
│     │   - 执行 auth.spec.ts                                       │  │
│     │   - 报告结果到 orchestrator                                 │  │
│     └─────────────────────────────────────────────────────────────┘  │
│     ┌─────────────────────────────────────────────────────────────┐  │
│     │ Agent 2: chat-e2e-agent                                     │  │
│     │   - 连接到 Playwright browser                               │  │
│     │   - 执行 chat.spec.ts                                       │  │
│     │   - 报告结果到 orchestrator                                 │  │
│     └─────────────────────────────────────────────────────────────┘  │
│     ┌─────────────────────────────────────────────────────────────┐  │
│     │ Agent 3: workspace-e2e-agent                                │  │
│     │   - 连接到 Playwright browser                               │  │
│     │   - 执行 threads.spec.ts + reconnect.spec.ts                │  │
│     │   - 报告结果到 orchestrator                                 │  │
│     └─────────────────────────────────────────────────────────────┘  │
│                                                                       │
│  4. Main Agent 汇总所有结果                                           │
│                                                                       │
│  5. Main Agent 更新 bug-reports.md (如有新问题)                       │
│                                                                       │
│  6. Main Agent 生成最终报告                                           │
└─────────────────────────────────────────────────────────────────────┘
```

## 任务委派示例

### 场景 1: 完整测试运行

```
User: "请运行完整的 E2E 测试套件，并汇报结果"

Main Agent:
1. 启动 3 个并行 agent (auth, chat, workspace)
2. 等待所有 agent 完成
3. 汇总结果
4. 输出报告
```

### 场景 2: 单套件测试

```
User: "auth 注册流程有问题，请单独测试 auth.spec.ts"

Main Agent:
1. 启动 auth-e2e-agent
2. 运行 auth.spec.ts
3. 详细报告结果
4. 如果失败，更新 bug-reports.md
```

### 场景 3: 问题验证

```
User: "上次报告的 BUG-001 看起来已修复，请重新测试验证"

Main Agent:
1. 启动 auth-e2e-agent
2. 运行相关测试
3. 验证 BUG-001 是否已解决
4. 更新 bug-reports.md (如已解决，标记 resolved)
```

## Bug Report 更新机制

### 自动更新

当 agent 发现测试失败时，自动更新 `bug-reports.md`:

```markdown
## New Bugs Found: 2026-05-27T10:30:00Z

| ID | 问题 | 原因 | 状态 | 套件 |
|----|------|------|------|------|
| BUG-001 | [auth] 登录失败后错误信息未显示 | SSE 响应解析错误 | open | auth |
```

### 手动关闭

```markdown
## Resolved

| ID | 问题 | 原因 | 解决方案 | 关闭日期 |
|----|------|------|----------|----------|
| BUG-001 | 登录失败后错误信息未显示 | 修复了 SSE 响应解析 | 在 chat.spec.ts 中添加了错误处理 | 2026-05-27 |
```

## 文件结构

```
tests/e2e/multi-agent/
├── orchestrator.ts     # Node.js 编排器
├── agents.ts          # Agent 配置文件
└── README.md          # 本文件
```

## 使用前提

1. 安装 Playwright: `pnpm playwright install`
2. 启动开发服务器: `pnpm dev`
3. 确保端口 3000 可用
