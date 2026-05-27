/**
 * E2E Multi-Agent Orchestrator
 *
 * 协调多个并行 E2E 测试 Agent，汇总结果并管理 bug reports
 *
 * 使用方式:
 *   npx tsx multi-agent/orchestrator.ts
 *   npx tsx multi-agent/orchestrator.ts --suite=auth
 *   npx tsx multi-agent/orchestrator.ts --watch
 */

import { spawn } from 'child_process';
import { writeFileSync, appendFileSync, existsSync } from 'fs';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const BASE_DIR = join(__dirname, '..', '..', '..');
const RESULTS_DIR = join(BASE_DIR, 'test-results');
const BUG_REPORT_PATH = join(BASE_DIR, 'bug-reports.md');

interface TestResult {
  name: string;
  specs: string[];
  passed: number;
  failed: number;
  duration: number;
  status: 'pass' | 'fail' | 'timeout';
  exitCode: number | null;
  output: string;
  errors: string[];
}

interface BugEntry {
  id: string;
  description: string;
  reason: string;
  status: 'open' | 'resolved';
  solution?: string;
  createdAt: string;
  resolvedAt?: string;
  suite?: string;
}

class E2EOrchestrator {
  private bugCounter = 0;
  private bugs: BugEntry[] = [];

  async run(suite?: string) {
    console.log('🚀 Starting E2E Multi-Agent Testing...\n');

    const suites = suite
      ? [{ name: suite, specs: this.getSpecsForSuite(suite) }]
      : this.getAllSuites();

    // 并行执行所有测试套件
    const results = await Promise.all(
      suites.map((s) => this.runTestSuite(s.name, s.specs))
    );

    // 汇总报告
    const summary = this.generateSummary(results);
    this.writeReport(summary, 'summary.md');

    // 更新 bug report
    this.updateBugReport(results);

    // 输出结果
    console.log('\n' + '='.repeat(50));
    console.log('✅ E2E Testing Complete!\n');
    console.log(summary);

    // 如果有失败的测试，退出码为 1
    const hasFailure = results.some((r) => r.status === 'fail');
    process.exit(hasFailure ? 1 : 0);
  }

  private getAllSuites() {
    return [
      {
        name: 'auth',
        specs: ['tests/e2e/auth.spec.ts'],
      },
      {
        name: 'chat',
        specs: ['tests/e2e/chat.spec.ts'],
      },
      {
        name: 'workspace',
        specs: ['tests/e2e/threads.spec.ts', 'tests/e2e/reconnect.spec.ts'],
      },
    ];
  }

  private getSpecsForSuite(suite: string): string[] {
    const map: Record<string, string[]> = {
      auth: ['tests/e2e/auth.spec.ts'],
      chat: ['tests/e2e/chat.spec.ts'],
      workspace: ['tests/e2e/threads.spec.ts', 'tests/e2e/reconnect.spec.ts'],
      threads: ['tests/e2e/threads.spec.ts'],
      reconnect: ['tests/e2e/reconnect.spec.ts'],
    };
    return map[suite] || [];
  }

  private async runTestSuite(name: string, specs: string[]): Promise<TestResult> {
    console.log(`📦 [${name}] Running: ${specs.join(', ')}`);

    const startTime = Date.now();
    const output: string[] = [];
    const errors: string[] = [];

    return new Promise((resolve) => {
      const args = [
        'playwright',
        'test',
        ...specs,
        '--reporter=list',
        '--output',
        join(RESULTS_DIR, name),
      ];

      const proc = spawn('pnpm', args, {
        cwd: BASE_DIR,
        stdio: ['ignore', 'pipe', 'pipe'],
      });

      proc.stdout?.on('data', (data) => {
        const text = data.toString();
        output.push(text);
        process.stdout.write(`  ${text}`);
      });

      proc.stderr?.on('data', (data) => {
        const text = data.toString();
        output.push(text);
        process.stderr.write(`  [error] ${text}`);
        errors.push(text);
      });

      proc.on('close', (code) => {
        const duration = Date.now() - startTime;
        const outputText = output.join('');

        // 解析测试结果
        const passed = (outputText.match(/✓|passed/gi) || []).length;
        const failed = (outputText.match(/✗|failed/gi) || []).length;

        resolve({
          name,
          specs,
          passed,
          failed,
          duration,
          status: code === 0 ? 'pass' : 'fail',
          exitCode: code,
          output: outputText,
          errors,
        });
      });

      proc.on('error', (err) => {
        errors.push(err.message);
        resolve({
          name,
          specs,
          passed: 0,
          failed: 1,
          duration: Date.now() - startTime,
          status: 'fail',
          exitCode: null,
          output: '',
          errors: [err.message],
        });
      });
    });
  }

  private generateSummary(results: TestResult[]): string {
    const totalPassed = results.reduce((sum, r) => sum + r.passed, 0);
    const totalFailed = results.reduce((sum, r) => sum + r.failed, 0);
    const totalDuration = results.reduce((sum, r) => sum + r.duration, 0);
    const allPassed = results.every((r) => r.status === 'pass');

    return `
# E2E Test Summary

**Run Date:** ${new Date().toISOString()}
**Duration:** ${(totalDuration / 1000).toFixed(1)}s
**Overall:** ${allPassed ? '✅ ALL PASSED' : '❌ SOME FAILED'}

## Results by Suite

${results
  .map(
    (r) => `
### ${r.name}
- **Status:** ${r.status === 'pass' ? '✅ PASS' : '❌ FAIL'}
- **Specs:** ${r.specs.join(', ')}
- **Passed:** ${r.passed}
- **Failed:** ${r.failed}
- **Duration:** ${(r.duration / 1000).toFixed(1)}s
${r.errors.length > 0 ? `- **Errors:**\n${r.errors.map((e) => `  - ${e}`).join('\n')}` : ''}
`
  )
  .join('\n')}

## Totals
- **Passed:** ${totalPassed}
- **Failed:** ${totalFailed}
- **Success Rate:** ${totalPassed + totalFailed > 0 ? ((totalPassed / (totalPassed + totalFailed)) * 100).toFixed(1) : 0}%
`;
  }

  private writeReport(content: string, filename: string) {
    const filepath = join(RESULTS_DIR, filename);
    writeFileSync(filepath, content);
    console.log(`\n📝 Report saved: ${filepath}`);
  }

  private updateBugReport(results: TestResult[]) {
    // 确保 bug-reports.md 存在
    if (!existsSync(BUG_REPORT_PATH)) {
      this.initBugReport();
    }

    // 收集新的 bug
    const newBugs = this.extractBugs(results);

    // 追加新的 bug
    if (newBugs.length > 0) {
      const timestamp = new Date().toISOString();
      const newEntries = newBugs
        .map(
          (b) =>
            `| ${b.id} | ${b.description} | ${b.reason} | ${b.status} | ${b.suite || ''} |`
        )
        .join('\n');

      const newSection = `\n## New Bugs Found: ${timestamp}\n\n| ID | 问题 | 原因 | 状态 | 套件 |\n|----|------|------|------|------|\n${newEntries}`;

      appendFileSync(BUG_REPORT_PATH, newSection);
      console.log(`\n🐛 ${newBugs.length} new bug(s) added to ${BUG_REPORT_PATH}`);
    }
  }

  private extractBugs(results: TestResult[]): BugEntry[] {
    const bugs: BugEntry[] = [];

    for (const result of results) {
      if (result.status === 'fail') {
        // 从错误输出中提取关键信息
        const errorLines = result.errors
          .join('\n')
          .split('\n')
          .filter((l) => l.includes('Error') || l.includes('fail'));

        for (const error of errorLines.slice(0, 3)) {
          this.bugCounter++;
          bugs.push({
            id: `BUG-${String(this.bugCounter).padStart(3, '0')}`,
            description: `[${result.name}] ${error.substring(0, 100)}`,
            reason: '需要进一步分析',
            status: 'open',
            createdAt: new Date().toISOString(),
            suite: result.name,
          });
        }
      }
    }

    return bugs;
  }

  private initBugReport() {
    const content = `# Bug Reports

## Format
| ID | 问题 | 原因 | 状态 | 套件 |

## Unresolved
| ID | 问题 | 原因 | 状态 | 套件 |
|----|------|------|------|------|

## Resolved
| ID | 问题 | 原因 | 解决方案 | 关闭日期 |
|----|------|------|----------|----------|
`;
    writeFileSync(BUG_REPORT_PATH, content);
    console.log(`\n📝 Initialized bug report: ${BUG_REPORT_PATH}`);
  }

  /** 添加手动 bug 报告 */
  addBug(description: string, reason: string, suite?: string): string {
    this.bugCounter++;
    const id = `BUG-${String(this.bugCounter).padStart(3, '0')}`;
    const bug: BugEntry = {
      id,
      description,
      reason,
      status: 'open',
      createdAt: new Date().toISOString(),
      suite,
    };
    this.bugs.push(bug);
    return id;
  }

  /** 解决一个 bug */
  resolveBug(id: string, solution: string) {
    const bug = this.bugs.find((b) => b.id === id);
    if (bug) {
      bug.status = 'resolved';
      bug.solution = solution;
      bug.resolvedAt = new Date().toISOString();
    }
  }
}

// CLI 入口
const args = process.argv.slice(2);
const suiteArg = args.find((a) => a.startsWith('--suite='));
const suite = suiteArg ? suiteArg.split('=')[1] : undefined;

const orchestrator = new E2EOrchestrator();
orchestrator.run(suite).catch(console.error);
