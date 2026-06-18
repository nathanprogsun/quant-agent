import type { Message } from "@langchain/langgraph-sdk";

/** Human-readable preview from a LangGraph submit payload. */
export function extractHumanTextFromSubmitValues(values: unknown): string {
  if (!values || typeof values !== "object") return "";
  const messages = (values as { messages?: unknown[] }).messages;
  if (!Array.isArray(messages)) return "";

  for (const message of messages) {
    if (!message || typeof message !== "object") continue;
    const typed = message as { type?: string; content?: unknown };
    if (typed.type !== "human") continue;
    if (typeof typed.content === "string") return typed.content.trim();
  }

  return "";
}

export function humanMessageFromContent(content: string): Message {
  return {
    id: `optimistic-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    type: "human",
    content,
  };
}
