import type { Message } from "@langchain/langgraph-sdk";
import { useStream } from "@langchain/langgraph-sdk/react";
import { useCallback, useEffect, useRef, useState } from "react";

import { getAPIClient } from "../api";

import type { AgentThreadState } from "./types";

// ── Message Identity ────────────────────────────────────────────────────────

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

// ── Merge Messages ──────────────────────────────────────────────────────────

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

export function mergeMessages(
  historyMessages: Message[],
  threadMessages: Message[],
  optimisticMessages: Message[],
): Message[] {
  const threadMessageIds = new Set(
    threadMessages.map(messageIdentity).filter(Boolean) as string[],
  );

  // Find overlap cutoff in history
  let cutoff = historyMessages.length;
  for (let i = historyMessages.length - 1; i >= 0; i--) {
    const msg = historyMessages[i];
    if (!msg) continue;
    const identity = messageIdentity(msg);
    if (identity && threadMessageIds.has(identity)) {
      cutoff = i;
    } else {
      break;
    }
  }

  return dedupeMessagesByIdentity([
    ...historyMessages.slice(0, cutoff),
    ...threadMessages,
    ...optimisticMessages,
  ]);
}

// ── Thread Stream Options ───────────────────────────────────────────────────

export interface ThreadStreamOptions {
  threadId?: string | null;
  assistantId?: string;
  onThreadId?: (threadId: string) => void;
  onCreated?: (meta: { thread_id: string; run_id: string }) => void;
  onFinish?: (state: { values: AgentThreadState }) => void;
}

// ── useThreadStream Hook ────────────────────────────────────────────────────

export function useThreadStream({
  threadId,
  assistantId = "lead_agent",
  onThreadId,
  onCreated,
  onFinish,
}: ThreadStreamOptions) {
  const [onStreamThreadId, setOnStreamThreadId] = useState(() => threadId);
  const [optimisticMessages, setOptimisticMessages] = useState<Message[]>([]);
  const listeners = useRef({ onCreated, onFinish, onThreadId });

  useEffect(() => {
    listeners.current = { onCreated, onFinish, onThreadId };
  }, [onCreated, onFinish, onThreadId]);

  useEffect(() => {
    setOnStreamThreadId(threadId ?? undefined);
  }, [threadId]);

  const thread = useStream<AgentThreadState>({
    client: getAPIClient(),
    assistantId,
    threadId: onStreamThreadId,
    reconnectOnMount: true,
    fetchStateHistory: { limit: 1 },
    onThreadId(newThreadId) {
      setOnStreamThreadId(newThreadId);
      listeners.current.onThreadId?.(newThreadId);
    },
    onCreated(meta) {
      listeners.current.onCreated?.({
        thread_id: meta.thread_id,
        run_id: meta.run_id,
      });
    },
    onFinish(state) {
      setOptimisticMessages([]);
      listeners.current.onFinish?.(state);
    },
  });

  const sendMessage = useCallback(
    (content: string) => {
      const optimistic: Message = {
        id: `optimistic-${Date.now()}`,
        type: "human",
        content,
      };
      setOptimisticMessages((prev) => [...prev, optimistic]);

      thread.submit({
        messages: [{ type: "human", content }],
      });
    },
    [thread],
  );

  const messages = mergeMessages(
    [],
    thread.messages,
    optimisticMessages,
  );

  return {
    ...thread,
    messages,
    sendMessage,
    clearOptimistic: () => setOptimisticMessages([]),
  };
}
