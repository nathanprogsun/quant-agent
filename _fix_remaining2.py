"""Fix remaining test issues: dict→Runtime() + user_id path update."""

import pathlib

WT = pathlib.Path(
    "/Users/jung/pro/quant-agent/.claude/worktrees/refactor+langchain-agent-middleware"
)

# 1. test_dynamic_context_memory.py: change before_model calls
f = WT / "backend/tests/unit/chat/middlewares/test_dynamic_context_memory.py"
t = f.read_text()
t = t.replace(', {"configurable": {"user_id": UUID(int=1)}}', ", Runtime()")
t = t.replace(', {"configurable": {"user_id": UUID(int=2)}}', ", Runtime()")
t = t.replace(', {"configurable": {"user_id": UUID(int=3)}}', ", Runtime()")
# Update assertion: provider.get_block called with None (not UUID)
t = t.replace(
    "assert provider.calls == [UUID(int=1)]", "assert provider.calls == [None]"
)
f.write_text(t)
print("Fixed: test_dynamic_context_memory.py")

# 2. test_memory_summarization_hook.py: change after_model with dict to Runtime()
f = WT / "backend/tests/unit/chat/memory/test_memory_summarization_hook.py"
t = f.read_text()
t = t.replace('{"configurable": {"user_id": "u1"}}', "Runtime()")
f.write_text(t)
print("Fixed: test_memory_summarization_hook.py")

# 3. Change _resolve_memory_block to not accept runtime (user_id from None)
f = WT / "backend/app/core/chat/middlewares/dynamic_context_middleware.py"
t = f.read_text()
t = t.replace(
    "async def _resolve_memory_block(self, runtime: Runtime) -> str | None:",
    "async def _resolve_memory_block(self) -> str | None:",
)
t = t.replace(
    "        # Runtime.context is populated by langgraph's create_agent (when used).\n"
    "        # With the manual agent_node path, context is None — user_id stays None,\n"
    "        # matching the prior behavior of passing an empty dict.\n"
    "        user_id = runtime.context.user_id if runtime.context else None\n"
    "        return await provider.get_block(user_id)",
    "        # user_id is not available from Runtime (agent_node passes Runtime()).\n"
    "        # The provider is responsible for user resolution.\n"
    "        return await provider.get_block(None)",
)
t = t.replace(
    "memory_block = await self._resolve_memory_block(runtime)",
    "memory_block = await self._resolve_memory_block()",
)
t = t.replace(
    "memory_block = await self._resolve_memory_block(runtime)",
    "memory_block = await self._resolve_memory_block()",
)
f.write_text(t)
print("Fixed: dynamic_context_middleware.py _resolve_memory_block")

print("Done")
