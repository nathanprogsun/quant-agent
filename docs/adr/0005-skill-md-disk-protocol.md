# ADR-0005 SKILL.md 磁盘协议替代内存 registry

- 状态：已采纳
- 关联代码：`backend/app/skills/storage/local_skill_storage.py`、`backend/app/core/chat/skills/registry.py`、`backend/app/web/api/skills/route.py`

## 背景

原 `app.core.chat.skills.registry.SkillRegistry` 为内存注册表（H2），skill 定义散落在代码中，无法运行时增删，且进程重启丢失。

## 决策

迁移到磁盘 SKILL.md 协议：

- **存储布局**：`<skills_root>/public/<name>/SKILL.md`（内置）+ `<skills_root>/custom/<name>/SKILL.md`（用户）；`custom/` 下附 `.history.jsonl` 追加式编辑历史
- **运行时开关**：`extensions_config.json` 的 `SkillStateConfig.enabled` 控制启用；lead_agent 装配时过滤 `enabled_skills`
- **路径安全**：所有读访问经路径穿越校验，限制在 `<root>` 内（`SkillPathTraversalError`）
- **遗留迁移**：`registry.py` 触发 `DeprecationWarning`，经 `scripts/migrate_legacy_skills.py` 迁移

## 结果

- 正面：skill 可热增删无需改代码；编辑历史可审计；与 `extensions_config.json` 统一运行时状态层
- 负面：`web/api/skills/route.py` 仍依赖 legacy `SkillRegistry`（`skill_registry_from_request`），迁移未完成——存在新旧两套并存的过渡期
