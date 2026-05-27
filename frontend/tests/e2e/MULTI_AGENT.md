# Multi-Subagent E2E Testing Architecture

## Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Orchestrator Agent                                  │
│                    (主协调器 - 任务分发与结果汇总)                            │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
          ┌──────────────────────────┼──────────────────────────┐
          ▼                          ▼                          ▼
┌─────────────────────┐    ┌─────────────────────┐    ┌─────────────────────┐
│   Auth E2E Agent    │    │   Chat E2E Agent    │    │  Workspace Agent    │
│  (注册/登录/登出)    │    │  (对话/流式/工具)   │    │  (线程管理/UI)      │
└─────────────────────┘    └─────────────────────┘    └─────────────────────┘
          │                          │                          │
          └──────────────────────────┼──────────────────────────┘
                                     ▼
                         ┌─────────────────────┐
                         │  Bug Reporter Agent  │
                         │  (问题收集与报告)     │
                         └─────────────────────┘
```

## Agent Definitions

### 1. Orchestrator Agent (主编排器)

**职责**：
- 解析测试需求，分解任务
- 并行调度 subagent
- 收集汇总结果
- 生成最终报告

**启动方式**：
```bash
# 在 backend-toolkit 项目中创建
/backend-toolkit/e2e-agents/orchestrator.ts
```

### 2. Auth E2E Agent

**测试域**：
- 用户注册 (register)
- 用户登录 (login)
- 登录失败处理
- 注册验证
- 登出功能

**Agent 配置**：
```yaml
name: auth-e2e-agent
description: Auth flow E2E testing agent
capabilities:
  - browser-control
  - api-mocking
tools:
  - playwright
context:
  testDir: ./tests/e2e
  specFile: auth.spec.ts
```

### 3. Chat E2E Agent

**测试域**：
- 消息发送
- SSE 流式响应
- 工具调用渲染
- 多行输入
- 乐观更新

**Agent 配置**：
```yaml
name: chat-e2e-agent
description: Chat conversation E2E testing agent
capabilities:
  - browser-control
  - sse-interception
tools:
  - playwright
context:
  testDir: ./tests/e2e
  specFile: chat.spec.ts
```

### 4. Workspace E2E Agent

**测试域**：
- 线程列表加载
- 线程创建
- 线程切换
- 重连机制

**Agent 配置**：
```yaml
name: workspace-e2e-agent
description: Workspace and threads E2E testing agent
capabilities:
  - browser-control
  - websocket-monitoring
tools:
  - playwright
context:
  testDir: ./tests/e2e
  specFiles:
    - threads.spec.ts
    - reconnect.spec.ts
```

## Execution Flow

```
1. orchestrator receives test request
         │
         ▼
2. orchestrator reads bug-reports.md (if exists)
         │
         ▼
3. orchestrator spawns 3 parallel agents:
   ┌──────────────────────────────────────────────┐
   │ Agent 1: Auth E2E                            │
   │  - Run auth.spec.ts                         │
   │  - Collect pass/fail results                │
   │  - Report bugs to bug-reports.md            │
   └──────────────────────────────────────────────┘
   ┌──────────────────────────────────────────────┐
   │ Agent 2: Chat E2E                            │
   │  - Run chat.spec.ts                         │
   │  - Collect pass/fail results                │
   │  - Report bugs to bug-reports.md            │
   └──────────────────────────────────────────────┘
   ┌──────────────────────────────────────────────┐
   │ Agent 3: Workspace E2E                       │
   │  - Run threads.spec.ts, reconnect.spec.ts   │
   │  - Collect pass/fail results                │
   │  - Report bugs to bug-reports.md            │
   └──────────────────────────────────────────────┘
         │
         ▼
4. orchestrator waits for all agents
         │
         ▼
5. orchestrator aggregates results
         │
         ▼
6. orchestrator generates final report
```

## Bug Report Format

```markdown
# Bug Reports

## Format
<!-- 问题编号 | 问题描述 | 问题原因 | 状态 -->

## Unresolved
| ID | 问题 | 原因 | 状态 |
|----|------|------|------|
| BUG-001 | [描述] | [原因] | open |
| BUG-002 | [描述] | [原因] | open |

## Resolved
| ID | 问题 | 原因 | 解决方案 | 关闭日期 |
|----|------|------|----------|----------|
| BUG-003 | [描述] | [原因] | [方案] | 2026-05-27 |
```

## Running the Multi-Agent E2E

### Option 1: Claude Code CLI

```bash
# 启动编排器
/claude-code -p "运行多 agent E2E 测试:
1. 启动 auth-e2e-agent 运行 auth.spec.ts
2. 启动 chat-e2e-agent 运行 chat.spec.ts
3. 启动 workspace-e2e-agent 运行 threads.spec.ts 和 reconnect.spec.ts
4. 汇总结果到 test-results/summary.md
5. 更新 bug-reports.md"
```

### Option 2: Script-based (推荐)

创建 `run-multi-agent-e2e.sh`:

```bash
#!/bin/bash
set -e

E2E_DIR="/Users/jung/pro/quant-agent/frontend"
REPORT_DIR="$E2E_DIR/test-results"

mkdir -p "$REPORT_DIR"

echo "🚀 Starting Multi-Agent E2E Testing..."
echo "========================================"

# 并行运行 3 个测试 agent
pnpm playwright test tests/e2e/auth.spec.ts --reporter=list &
PID_AUTH=$!

pnpm playwright test tests/e2e/chat.spec.ts --reporter=list &
PID_CHAT=$!

pnpm playwright test tests/e2e/threads.spec.ts tests/e2e/reconnect.spec.ts --reporter=list &
PID_WORKSPACE=$!

# 等待所有测试完成
wait $PID_AUTH
AUTH_RESULT=$?

wait $PID_CHAT
CHAT_RESULT=$?

wait $PID_WORKSPACE
WORKSPACE_RESULT=$?

# 生成汇总报告
echo "========================================" 
echo "📊 Generating Summary Report..."

cat > "$REPORT_DIR/summary.md" << EOF
# E2E Test Summary

**Run Date:** $(date)
**Auth:** $([ $AUTH_RESULT -eq 0 ] && echo "✅ PASS" || echo "❌ FAIL")
**Chat:** $([ $CHAT_RESULT -eq 0 ] && echo "✅ PASS" || echo "❌ FAIL")
**Workspace:** $([ $WORKSPACE_RESULT -eq 0 ] && echo "✅ PASS" || echo "❌ FAIL")
EOF

echo "✅ Multi-Agent E2E Testing Complete!"
```

### Option 3: Node.js Orchestrator (推荐)

创建 `tests/e2e/multi-agent/runner.ts`:

```typescript
import { spawn } from 'child_process';
import { writeFileSync, appendFileSync, existsSync, mkdirSync } from 'fs';

interface TestResult {
  name: string;
  passed: number;
  failed: number;
  duration: number;
  status: 'pass' | 'fail';
}

interface BugReport {
  id: string;
  description: string;
  reason: string;
  status: 'open' | 'resolved';
  solution?: string;
  createdAt: string;
  resolvedAt?: string;
}

class E2EOrchestrator {
  private baseDir = '/Users/jung/pro/quant-agent/frontend';
  private resultsDir = `${this.baseDir}/test-results`;
  private bugReportPath = `${this.baseDir}/bug-reports.md`;

  async run() {
    console.log('🚀 Starting E2E Multi-Agent Testing...\n');

    // 确保目录存在
    mkdirSync(this.resultsDir, { recursive: true });

    // 并行执行所有测试域
    const results = await Promise.all([
      this.runTestSuite('auth', 'tests/e2e/auth.spec.ts'),
      this.runTestSuite('chat', 'tests/e2e/chat.spec.ts'),
      this.runTestSuite('workspace', ['tests/e2e/threads.spec.ts', 'tests/e2e/reconnect.spec.ts']),
    ]);

    // 汇总报告
    const summary = this.generateSummary(results);
    this.writeReport(summary);
    this.updateBugReport();

    console.log('\n✅ E2E Testing Complete!');
    console.log(summary);
  }

  private async runTestSuite(name: string, specs: string | string[]): Promise<TestResult> {
    const specFiles = Array.isArray(specs) ? specs.join(' ') : specs;
    console.log(`📦 Running ${name} tests: ${specFiles}`);

    return new Promise((resolve) => {
      const start = Date.now();
      const process = spawn('pnpm', ['playwright', 'test', specFiles, '--reporter=list', 'json'], {
        cwd: this.baseDir,
        stdio: ['ignore', 'pipe', 'pipe']
      });

      let output = '';
      process.stdout?.on('data', (data) => { output += data.toString(); });
      process.stderr?.on('data', (data) => { output += data.toString(); });

      process.on('close', (code) => {
        const duration = Date.now() - start;
        const passed = (output.match(/✓/g) || []).length;
        const failed = (output.match(/✗/g) || []).length;

        resolve({
          name,
          passed,
          failed,
          duration,
          status: code === 0 ? 'pass' : 'fail'
        });
      });
    });
  }

  private generateSummary(results: TestResult[]): string {
    const total = results.reduce((acc, r) => ({
      passed: acc.passed + r.passed,
      failed: acc.failed + r.failed,
      duration: acc.duration + r.duration
    }), { passed: 0, failed: 0, duration: 0 });

    return `
# E2E Test Summary

**Run Date:** ${new Date().toISOString()}
**Total:** ${total.passed + total.failed} tests
**Passed:** ${total.passed}
**Failed:** ${total.failed}
**Duration:** ${(total.duration / 1000).toFixed(1)}s

## Results by Suite

${results.map(r => `
### ${r.name}
- Status: ${r.status === 'pass' ? '✅' : '❌'}
- Passed: ${r.passed}
- Failed: ${r.failed}
- Duration: ${(r.duration / 1000).toFixed(1)}s
`).join('\n')}
`;
  }

  private writeReport(summary: string) {
    writeFileSync(`${this.resultsDir}/summary.md`, summary);
  }

  private updateBugReport() {
    if (!existsSync(this.bugReportPath)) {
      this.initBugReport();
    }
    // 追加测试运行信息
    appendFileSync(this.bugReportPath, `\n## Test Run: ${new Date().toISOString()}\n`);
  }

  private initBugReport() {
    const content = `# Bug Reports

## Format
<!-- ID | 问题描述 | 问题原因 | 状态 -->

## Unresolved
| ID | 问题 | 原因 | 状态 |
|----|------|------|------|

## Resolved
| ID | 问题 | 原因 | 解决方案 | 关闭日期 |
|----|------|------|----------|----------|
`;
    writeFileSync(this.bugReportPath, content);
  }
}

// 运行
new E2EOrchestrator().run();
```

## Bug Report Workflow

```
┌─────────────────────────────────────────────────────────────┐
│                    Bug Report Lifecycle                      │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│  1. Agent 发现问题                                           │
│     - 测试失败                                               │
│     - 截图捕获                                               │
│     - 控制台日志                                             │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│  2. 记录到 bug-reports.md                                    │
│     - 分配唯一 ID (BUG-001, BUG-002...)                      │
│     - 描述问题现象                                           │
│     - 分析可能原因                                           │
│     - 标记 status: open                                     │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│  3. 后续 Agent 检查                                         │
│     - 读取未解决的 bug                                       │
│     - 尝试复现                                               │
│     - 如果修复，标记 status: resolved + 解决方案             │
└─────────────────────────────────────────────────────────────┘
```

## Example Bug Report Entry

```markdown
## Unresolved

| BUG-001 | SSE 流响应丢失最后一条消息 | 后端在 end event 前未正确 flush | open |
| BUG-002 | 线程切换后聊天记录未清空 | React state 未正确重置 | open |
```

## Next Steps

1. 创建 `bug-reports.md` 文件
2. 运行 `run-multi-agent-e2e.sh` 执行测试
3. 定期 review `bug-reports.md` 解决未关闭的问题
