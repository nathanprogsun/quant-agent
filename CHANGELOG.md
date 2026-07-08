# Changelog

本项目遵循 [Conventional Commits](https://www.conventionalcommits.org/)。

## [Unreleased]

### Fixed

- **dev**: 修复前端 `next dev`(Turbopack) 启动后卡在 `Compiling /`、postcss worker fork 爆炸(500+→1200+ 僵尸进程)导致页面无法打开的问题。根因为从 npm 迁移到 pnpm 后，pnpm 默认 symlink 非扁平 `node_modules` 与 Turbopack 不兼容，postcss worker 子进程无法解析 `.pnpm/` 间接路径而静默崩溃，Turbopack 反复重启 worker。修复：新增 `frontend/.npmrc` 配置 `node-linker=hoisted`，`pnpm install` 产出扁平 `node_modules` 以兼容 Turbopack；同步移除残留的 `package-lock.json`。同时 `.vscode/launch.json` 的 `Next.js: Frontend Dev` 配置加 `autoAttachChildProcesses: false`，避免调试器 attach 到 worker。
- **fix(frontend)**: 修复整应用客户端组件不水合(hydration)导致登录表单与发消息按钮完全无响应的 bug。根因：Next.js 16 默认阻断非预期 origin 对 dev 资源(含 HMR websocket `_next/webpack-hmr`)的跨域访问，`127.0.0.1` 未被允许 → HMR websocket 握手失败(`ERR_INVALID_HTTP_RESPONSE`) → Turbopack 下 hydration 入口与 HMR 客户端绑定 → hydration 从未初始化 → React 不 attach 事件、`<html>` 无 `__react` fiber。修复：`next.config.ts` 新增 `allowedDevOrigins: ["127.0.0.1", "localhost"]`。该 bug 由真实 E2E（puppeteer-core + 系统 Chrome 跑真实后端）捕获，mock-based 测试无法发现。

### Changed

- **test**: 移除前端 Vitest + Testing Library + jsdom + Playwright 测试栈，改用 `puppeteer-core` + 系统 Chrome 做**真实**前端 E2E（`pnpm test:e2e` = `node e2e/run.mjs`，基于 Node 内置 `node:test`，零浏览器下载）。harness 自动拉起/复用真实后端(uvicorn + 独立 sqlite 测试库，自动建表)+ 真实前端，跑真实用户流：未登录重定向、真实后端注册+cookie+SSR 鉴权+workspace 渲染、登录表单水合、发消息→真实建线程→真实 LLM 流式回复。测试隔离用 incognito context 防止 cookie 跨用例泄漏，交互前 `waitForReactReady` 等水合就绪。同步清理 `vitest.config.ts`、`playwright.config.ts`、`tests/`、`e2e/`(playwright 规格)、`playwright-report/`、`test-results/` 及 `src/**/*.test.*` 组件测试。`package.json` 的 `test`/`test:watch`/`test:e2e`(playwright) 脚本移除，新增 `test:e2e`(puppeteer)。后端 endpoint 自动化测试由 `tests/integration/`(pytest + ASGITransport) 覆盖，`make test` 不变。AGENTS.md / README 测试命令同步更新。
- **test(分层)**: 真实 E2E 较慢(10-60s + LLM 流式)，不宜每次 commit 跑。调整 commit 前检查为 `make test`(后端) + `pnpm lint` + `pnpm exec tsc --noEmit`；`pnpm test:e2e` 降级为按需(改了前端交互/鉴权/workspace 渲染、合入 main 前、CI)。新增 `pnpm test:e2e:smoke`(`E2E_SMOKE=1`，只跑 auth.test 不依赖 LLM，~5s) 与 `pnpm typecheck`(`tsc --noEmit`) 脚本。AGENTS.md / README 同步更新测试分层说明。
