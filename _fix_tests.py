"""Fix test files: add Runtime import, change {} to Runtime() in hook calls."""

import pathlib

WORKTREE = pathlib.Path(
    "/Users/jung/pro/quant-agent/.claude/worktrees/refactor+langchain-agent-middleware"
)

test_files = [
    "backend/tests/unit/test_title_middleware.py",
    "backend/tests/unit/test_lead_agent.py",
    "backend/tests/unit/chat/memory/test_memory_summarization_hook.py",
    "backend/tests/unit/chat/middlewares/test_dynamic_context_id_stable.py",
    "backend/tests/unit/chat/middlewares/test_memory_writeback_hook.py",
    "backend/tests/unit/chat/middlewares/test_dynamic_context_memory.py",
    "backend/tests/unit/chat/middlewares/test_token_usage_subagent_bridge.py",
]

for rel in test_files:
    f = WORKTREE / rel
    text = f.read_text()

    # Add Runtime import after Runtime import
    text = text.replace(
        "from app.core.chat.middlewares.base import AgentMiddleware",
        "from app.core.chat.middlewares.base import AgentMiddleware, Runtime",
    )

    # Change {} to Runtime() in hook calls
    text = text.replace("before_model(state, {})", "before_model(state, Runtime())")
    text = text.replace("before_model(state, {}, ),", "before_model(state, Runtime()),")
    text = text.replace("after_model(state, {})", "after_model(state, Runtime())")

    # Remove before_tool/after_tool test calls (these methods are dead code, removed)
    # test_subagent_limit_middleware.py has before_tool calls
    f.write_text(text)
    print(f"Fixed: {rel}")

# Also fix test_subagent_limit_middleware.py (has before_tool calls + before_model calls)
slm = WORKTREE / "backend/tests/unit/chat/middlewares/test_subagent_limit_middleware.py"
text = slm.read_text()
text = text.replace(
    "from app.core.chat.middlewares.base import AgentMiddleware",
    "from app.core.chat.middlewares.base import AgentMiddleware, Runtime",
)
text = text.replace("before_model(state, {})", "before_model(state, Runtime())")
# Remove before_tool/after_tool test methods (dead code)

# Remove the test_limits_active_count_with_before_tool function and similar
lines = text.split("\n")
new_lines = []
skip = False
for i, line in enumerate(lines):
    if "def test_" in line and (
        "before_tool" in lines[i] or "after_tool" in lines[i] or "tool_name" in lines[i]
    ):
        # Check if preceding def is a tool test
        pass

    if "test_limits_active_count_with_before_tool" in line:
        skip = True
    elif "test_limits_active_count_with_before_tool" in line:
        skip = True
    elif "test_tool_count_increments_on_before_tool" in line:
        skip = True
    elif "test_tool_count_decrements_on_after_tool" in line:
        skip = True

    if not skip:
        new_lines.append(line)

    # End skip on next def or EOF
    if skip and line.strip().startswith("def test_") and "tool" not in line:
        # stopped skipping too early
        pass
    if skip and line.strip().startswith("def") and "tool" not in line.split("_"):
        new_lines.append(line)
        skip = False

slm.write_text("\n".join(new_lines))
print("Fixed: test_subagent_limit_middleware.py")

print("\nDone.")
