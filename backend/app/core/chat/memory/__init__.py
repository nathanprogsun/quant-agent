"""Memory evolution subsystem (P4.5)."""

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

__all__ = [
    "FACT_EXTRACTION_PROMPT",
    "MEMORY_UPDATE_PROMPT",
    "ExistingFact",
    "MemoryUpdateQueue",
    "MemoryUpdateResult",
    "MemoryUpdater",
    "NewFact",
    "SummarizationEvent",
    "memory_flush_hook",
    "prune_facts",
]
