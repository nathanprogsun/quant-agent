import type { Message } from "@langchain/langgraph-sdk";

/**
 * Message identity for deduplication.
 * Uses message.id or tool_call_id as unique key.
 */
function getMessageIdentity(message: Message): string | null {
  if (message.id) return message.id;
  if ("tool_call_id" in message && message.tool_call_id) {
    return `tool:${message.tool_call_id}`;
  }
  return null;
}

/**
 * Merge three message sources with O(1) deduplication.
 *
 * Priority: optimistic > stream > history
 * - optimistic: user messages not yet confirmed by server
 * - stream: real-time SSE messages (highest server priority)
 * - history: loaded from backend (may overlap with stream on reconnect)
 */
export function mergeMessages(
  history: Message[],
  stream: Message[],
  optimistic: Message[],
): Message[] {
  const seen = new Map<string, Message>();
  const result: Message[] = [];

  // 1. Add history messages (lowest priority)
  for (const msg of history) {
    const key = getMessageIdentity(msg);
    if (key) {
      seen.set(key, msg);
      result.push(msg);
    } else {
      result.push(msg);
    }
  }

  // 2. Merge stream messages (higher priority — overwrites history)
  for (const msg of stream) {
    const key = getMessageIdentity(msg);
    if (key) {
      if (seen.has(key)) {
        const idx = result.findIndex(
          (m) => getMessageIdentity(m) === key,
        );
        if (idx !== -1) result[idx] = msg;
      } else {
        result.push(msg);
      }
      seen.set(key, msg);
    } else {
      result.push(msg);
    }
  }

  // 3. Merge optimistic messages (highest priority)
  for (const msg of optimistic) {
    const key = getMessageIdentity(msg);
    if (key) {
      if (seen.has(key)) {
        const idx = result.findIndex(
          (m) => getMessageIdentity(m) === key,
        );
        if (idx !== -1) result[idx] = msg;
      } else {
        result.push(msg);
      }
      seen.set(key, msg);
    } else {
      result.push(msg);
    }
  }

  return result;
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
    const key = getMessageIdentity(msg);
    if (key) seen.add(key);
  }

  const newMessages: Message[] = [];
  for (const msg of incoming) {
    const key = getMessageIdentity(msg);
    if (!key || !seen.has(key)) {
      newMessages.push(msg);
    }
  }

  return newMessages.length > 0 ? [...existing, ...newMessages] : existing;
}
