# Changelog

本项目遵循 [Conventional Commits](https://www.conventionalcommits.org/)。

## [Unreleased]

### Fixed

- **dev**: 修复前端 `next dev`(Turbopack) 启动后卡在 `Compiling /`、postcss worker fork 爆炸(500+→1200+ 僵尸进程)导致页面无法打开的问题。根因为从 npm 迁移到 pnpm 后，pnpm 默认 symlink 非扁平 `node_modules` 与 Turbopack 不兼容，postcss worker 子进程无法解析 `.pnpm/` 间接路径而静默崩溃，Turbopack 反复重启 worker。修复：新增 `frontend/.npmrc` 配置 `node-linker=hoisted`，`pnpm install` 产出扁平 `node_modules` 以兼容 Turbopack；同步移除残留的 `package-lock.json`。同时 `.vscode/launch.json` 的 `Next.js: Frontend Dev` 配置加 `autoAttachChildProcesses: false`，避免调试器 attach 到 worker。
