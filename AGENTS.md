## 规则
- 后端用uv, 不用pip
- 前端使用pnpm, 不用npm
- commit前跑 make test(后端) + pnpm lint(前端) + pnpm exec tsc --noEmit(前端类型检查)
- pnpm test:e2e(真实 E2E，慢、依赖 LLM) 仅在改了前端交互/鉴权/workspace 渲染、合入 main 前、或 CI 里按需跑；不强制每次 commit
- Conventional Commits(feat/fix/docs/refactor/chore)
- commit 到main,不走PR
- 不做reset --hard/clean, 除非我明确要求
- 新依赖需做健康检查
- 改行为时更新 docs/ 和 CHANGELOG.md
-


## 技术栈
- 后端: python 3.11+ / uv / langgraph / langchain-core / pytest / ruff / mypy
- 前端：Next.js / pnpm / TypeScript
- 数据：ChromaDB / SQLite / Kùzu

## 文档位置
- 架构决策：docs/architecture.md
- 产品规范：docs/spec.md
- 实现计划：docs/<feature>-plan.md

## 禁止
- 不擅自换包管理器
- 不引入新框架，除非我同意
- 不做全局 search/replace
