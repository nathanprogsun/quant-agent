"""Fix remaining: test files {}→Runtime(), middleware bodies config.→runtime.context."""

import pathlib

WT = pathlib.Path(
    "/Users/jung/pro/quant-agent/.claude/worktrees/refactor+langchain-agent-middleware"
)

# 1. Fix test files: add Runtime import + change {} to Runtime()
test_files = [
    "backend/tests/unit/test_lead_agent.py",
    "backend/tests/unit/test_title_middleware.py",
    "backend/tests/unit/chat/middlewares/test_dynamic_context_id_stable.py",
    "backend/tests/unit/chat/middlewares/test_dynamic_context_memory.py",
    "backend/tests/unit/chat/middlewares/test_memory_writeback_hook.py",
    "backend/tests/unit/chat/middlewares/test_token_usage_subagent_bridge.py",
    "backend/tests/unit/chat/memory/test_memory_summarization_hook.py",
    "backend/tests/unit/chat/middlewares/test_subagent_limit_middleware.py",
]

for rel in test_files:
    f = WT / rel
    if not f.exists():
        continue
    text = f.read_text()

    # Add Runtime import where base.AgentMiddleware is imported
    text = text.replace(
        "from app.core.chat.middlewares.base import AgentMiddleware",
        "from app.core.chat.middlewares.base import AgentMiddleware, Runtime",
    )
    # Also handle direct langgraph.runtime imports
    if "Runtime" not in text:
        text = text.replace(
            "from langchain_core.messages import",
            "from langgraph.runtime import Runtime\nfrom langchain_core.messages import",
        )

    # Change {} to Runtime() in hook calls
    text = text.replace("before_model(state, {})", "before_model(state, Runtime())")
    text = text.replace("after_model(state, {})", "after_model(state, Runtime())")
    text = text.replace(
        "after_model({'messages': messages}, {'configurable': {'user_id': 'u1'}})",
        "after_model({'messages': messages}, Runtime())",
    )
    text = text.replace("after_model(state, config)", "after_model(state, Runtime())")

    # Fix before_model calls with { configurable: ... }
    import re

    # pattern: before_model(state, {"configurable": {"user_id": ...} })
    text = re.sub(
        r"before_model\(state,\s*\{[^}]*\}\)", "before_model(state, Runtime())", text
    )

    f.write_text(text)
    print(f"Fixed: {rel}")

# 2. Fix middleware bodies that still reference config (param renamed to runtime)
for rel, replacements in [
    (
        "backend/app/core/chat/middlewares/memory_middleware.py",
        [
            (
                'configurable = config.get("configurable", {})\n        thread_id = str(configurable.get("thread_id", "")) or "unknown"\n        user_id = configurable.get("user_id")',
                'thread_id = str(runtime.context.thread_id if runtime.context else "") or "unknown"\n        user_id = runtime.context.user_id if runtime.context else None',
            ),
        ],
    ),
    (
        "backend/app/core/chat/middlewares/summarization_middleware.py",
        [
            (
                'configurable = config.get("configurable", {})\n        thread_id = str(configurable.get("thread_id", "")) or "unknown"\n        user_id = configurable.get("user_id")',
                'thread_id = str(runtime.context.thread_id if runtime.context else "") or "unknown"\n        user_id = runtime.context.user_id if runtime.context else None',
            ),
        ],
    ),
]:
    f = WT / rel
    text = f.read_text()
    for old, new in replacements:
        if old not in text:
            print(f"{rel}: WARNING — pattern not found, trying partial")
            # Try partial match
            if 'config.get("configurable"' in text:
                text = text.replace(
                    'config.get("configurable", {})',
                    '{"thread_id": str(runtime.context.thread_id if runtime.context else ""), "user_id": runtime.context.user_id if runtime.context else None}',
                )
        else:
            text = text.replace(old, new)
    f.write_text(text)
    print(f"Fixed: {rel}")
print("Done")
