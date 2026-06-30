"""Memory evolution subsystem (P4.5)."""

from app.core.chat.memory.llm_adapter import MemoryLLMAdapter
from app.core.chat.memory.prompt import FACT_EXTRACTION_PROMPT, MEMORY_UPDATE_PROMPT
from app.core.chat.memory.queue import MemoryUpdateQueue
from app.core.chat.memory.summarization_hook import (
    SummarizationEvent,
    memory_flush_hook,
)
from app.core.chat.memory.updater import (
    ExistingFact,
    MemoryUpdater,
    MemoryUpdateResult,
    NewFact,
    prune_facts,
)
from app.core.chat.memory.wiring import (
    build_memory_update_queue,
    install_memory_subsystem,
    shutdown_memory_subsystem,
)

__all__ = [
    "FACT_EXTRACTION_PROMPT",
    "MEMORY_UPDATE_PROMPT",
    "ExistingFact",
    "MemoryLLMAdapter",
    "MemoryUpdateQueue",
    "MemoryUpdateResult",
    "MemoryUpdater",
    "NewFact",
    "SummarizationEvent",
    "build_memory_update_queue",
    "install_memory_subsystem",
    "memory_flush_hook",
    "prune_facts",
    "shutdown_memory_subsystem",
]
