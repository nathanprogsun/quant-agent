"""Prompts for LLM-driven memory evolution (P4.5).

Ports deer-flow's ``agents/memory/prompt.py`` contract: the LLM receives a
conversation and must return a JSON object with the four canonical keys
(``user``, ``history``, ``newFacts``, ``factsToRemove``).

Note: ``{conversation}`` / ``{text}`` are plain placeholders substituted via
``str.replace`` (not ``str.format``) so the JSON braces need no escaping.
"""

from __future__ import annotations

MEMORY_UPDATE_PROMPT = """You are a memory extraction agent for a quantitative-investment assistant.

Analyze the conversation below and update the user's long-term memory.
Return ONLY a JSON object with exactly these keys:

{
  "user": "<one-line summary of the user's profile/preferences>",
  "history": ["<recent interaction summaries, newest last>"],
  "newFacts": [
    {
      "content": "<the fact>",
      "fact_type": "user|preference|behavior|correction|context",
      "category": "<category, use 'correction' for user corrections>",
      "confidence": <0.0-1.0>
    }
  ],
  "factsToRemove": ["<content of stale facts to delete>"]
}

Rules:
- Only extract durable facts, not transient queries.
- Confidence reflects how certain the fact is (0.0-1.0).
- User corrections must use category 'correction'.
- Output must be valid JSON. No prose, no markdown fences.

Conversation:
{conversation}
"""

FACT_EXTRACTION_PROMPT = """Extract structured facts from the following text.

Return ONLY a JSON array of objects with keys: content, fact_type, category, confidence.
Text:
{text}
"""

__all__ = ["FACT_EXTRACTION_PROMPT", "MEMORY_UPDATE_PROMPT"]
