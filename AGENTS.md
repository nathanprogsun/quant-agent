## 规则
- 后端用uv, 不用pip
- 前端使用pnpm, 不用npm
- commit前跑make test(后端) + pnpm test:e2e(前端)
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
