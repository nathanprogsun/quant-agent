import type { Message } from "@langchain/langgraph-sdk";

import { extractContentFromMessage } from "./utils";

function messageIdentity(message: Message): string | undefined {
  if (
    "tool_call_id" in message &&
    typeof message.tool_call_id === "string" &&
    message.tool_call_id.length > 0
  ) {
    return `tool:${message.tool_call_id}`;
  }
  if (typeof message.id === "string" && message.id.length > 0) {
    return `message:${message.id}`;
  }
  return undefined;
}

function dedupeMessagesByIdentity(messages: Message[]): Message[] {
  const lastIndexByIdentity = new Map<string, number>();

  messages.forEach((message, index) => {
    const identity = messageIdentity(message);
    if (identity) lastIndexByIdentity.set(identity, index);
  });

  return messages.filter((message, index) => {
    const identity = messageIdentity(message);
    return !identity || lastIndexByIdentity.get(identity) === index;
  });
}

/** Normalize LangChain checkpoint dict messages into SDK Message shape. */
export function normalizeCheckpointMessage(message: Message): Message {
  if (typeof message.content === "string" || Array.isArray(message.content)) {
    return message;
  }

  const data = (message as Message & {
    data?: { content?: unknown; id?: string };
  }).data;

  if (!data) return message;

  return {
    ...message,
    id: message.id ?? data.id,
    content: data.content as Message["content"],
  };
}

export function normalizeCheckpointMessages(messages: Message[]): Message[] {
  return messages.map(normalizeCheckpointMessage);
}

/** Drop optimistic human messages once the stream has confirmed the same text. */
export function filterConfirmedOptimistic(
  stream: Message[],
  optimistic: Message[],
): Message[] {
  if (optimistic.length === 0) return optimistic;

  const confirmedHumanContent = new Set(
    stream
      .filter((message) => message.type === "human")
      .map((message) => extractContentFromMessage(message))
      .filter(Boolean),
  );

  return optimistic.filter((message) => {
    if (message.type !== "human") return true;
    const content = extractContentFromMessage(message);
    return !content || !confirmedHumanContent.has(content);
  });
}

/**
 * Merge thread messages for display.
 *
 * LangGraph SDK `messages` already reflects `stream.values ?? historyValues`.
 * Do not concatenate history checkpoint messages on top — that duplicates turns.
 * History is only used before stream hydration (initial thread load).
 */
export function mergeMessages(
  history: Message[],
  stream: Message[],
  optimistic: Message[],
): Message[] {
  const normalizedHistory = normalizeCheckpointMessages(history);
  const base = stream.length > 0 ? stream : normalizedHistory;
  const confirmationSource = stream.length > 0 ? stream : base;
  const pendingOptimistic = filterConfirmedOptimistic(
    confirmationSource,
    optimistic,
  );

  return dedupeMessagesByIdentity([...base, ...pendingOptimistic]);
}

/**
 * Incremental merge: only merge new messages into existing list.
 * Avoids re-merging the entire history on each SSE chunk.
 */
export function mergeIncremental(
  existing: Message[],
  incoming: Message[],
): Message[] {
  if (incoming.length === 0) return existing;
  if (existing.length === 0) return incoming;

  const seen = new Set<string>();
  for (const msg of existing) {
    const key = messageIdentity(msg);
    if (key) seen.add(key);
  }

  const newMessages: Message[] = [];
  for (const msg of incoming) {
    const key = messageIdentity(msg);
    if (!key || !seen.has(key)) {
      newMessages.push(msg);
    }
  }

  return newMessages.length > 0 ? [...existing, ...newMessages] : existing;
}
