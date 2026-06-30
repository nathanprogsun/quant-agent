"""Refactor middleware hooks: config: dict → runtime: Runtime."""

import pathlib

BASE = pathlib.Path(
    "/Users/jung/pro/quant-agent/.claude/worktrees/refactor+langchain-agent-middleware/backend"
)

replacements = {
    "app/core/chat/middlewares/dynamic_context_middleware.py": [
        (
            "    async def before_model(\n        self, state: dict[str, Any], config: dict[str, Any]",
            "    async def before_model(\n        self, state: dict[str, Any], runtime: Runtime",
        ),
        (
            "    async def _resolve_memory_block(self, config: dict[str, Any]) -> str | None:",
            "    async def _resolve_memory_block(self, runtime: Runtime) -> str | None:",
        ),
        (
            "memory_block = await self._resolve_memory_block(config)",
            "memory_block = await self._resolve_memory_block(runtime)",
        ),
    ],
    "app/core/chat/middlewares/memory_middleware.py": [
        (
            "    async def before_model(\n        self, state: dict[str, Any], config: dict[str, Any]",
            "    async def before_model(\n        self, state: dict[str, Any], runtime: Runtime",
        ),
        (
            "    async def after_model(\n        self, state: dict[str, Any], config: dict[str, Any]",
            "    async def after_model(\n        self, state: dict[str, Any], runtime: Runtime",
        ),
    ],
    "app/core/chat/middlewares/subagent_limit_middleware.py": [
        (
            "    async def before_model(\n        self, state: dict[str, Any], config: dict[str, Any]",
            "    async def before_model(\n        self, state: dict[str, Any], runtime: Runtime",
        ),
    ],
    "app/core/chat/middlewares/summarization_middleware.py": [
        (
            "    async def before_model(\n        self, state: dict[str, Any], config: dict[str, Any]",
            "    async def before_model(\n        self, state: dict[str, Any], runtime: Runtime",
        ),
        (
            "    async def after_model(\n        self, state: dict[str, Any], config: dict[str, Any]",
            "    async def after_model(\n        self, state: dict[str, Any], runtime: Runtime",
        ),
    ],
    "app/core/chat/agent/lead_agent.py": [
        (
            "modified = await mw.before_model(working_state, {})",
            "modified = await mw.before_model(working_state, Runtime())",
        ),
        (
            "modified = await mw.after_model(preview_state, {})",
            "modified = await mw.after_model(preview_state, Runtime())",
        ),
    ],
}

# Remove before_tool/after_tool blocks (dead code)
dcm_lines = (
    (BASE / "app/core/chat/middlewares/loop_detection_middleware.py")
    .read_text()
    .split("\n")
)
# Find before_tool def, after_tool def, remove both blocks
new_lines = []
skip_block = False
in_btool = False
in_atool = False
btool_lines = 0
for i, line in enumerate(dcm_lines):
    if line.strip().startswith("async def before_tool("):
        in_btool = True
        btool_lines = 0
        continue
    if in_btool:
        btool_lines += 1
        if line.strip() == "" and btool_lines > 2:  # blank line after method body
            in_btool = False
            continue
        continue
    if line.strip().startswith("async def after_tool("):
        in_atool = True
        continue
    if in_atool:
        if line.strip() == "" and line == dcm_lines[min(i + 1, len(dcm_lines) - 1)]:
            # keep one blank after removal
            pass
        if line.strip() == "":
            in_atool = False
        continue
    new_lines.append(line)
(BASE / "app/core/chat/middlewares/loop_detection_middleware.py").write_text(
    "\n".join(new_lines)
)

# Subagent limit: remove before_tool/after_tool
slm_lines = (
    (BASE / "app/core/chat/middlewares/subagent_limit_middleware.py")
    .read_text()
    .split("\n")
)
new_lines = []
in_btool = False
in_atool = False
btool_done = False
for line in slm_lines:
    if line.strip().startswith("async def before_tool("):
        in_btool = True
        continue
    if in_btool:
        if line.strip() == "":
            in_btool = False
        continue
    if line.strip().startswith("async def after_tool("):
        in_atool = True
        continue
    if in_atool:
        if line.strip() == "":
            in_atool = False
        continue
    new_lines.append(line)
(BASE / "app/core/chat/middlewares/subagent_limit_middleware.py").write_text(
    "\n".join(new_lines)
)

# Apply text replacements for the remaining files
for filepath, pairs in replacements.items():
    f = BASE / filepath
    text = f.read_text(encoding="utf-8")
    for old, new in pairs:
        assert old in text, f"{filepath}: pattern NOT FOUND:\n{old[:80]}"
        text = text.replace(old, new)
    f.write_text(text, encoding="utf-8")

print("All replacements done")
