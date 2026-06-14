import type { Message } from "@langchain/langgraph-sdk";
import { useStream } from "@langchain/langgraph-sdk/react";
import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";

import {
  filterConfirmedOptimistic,
  mergeMessages,
  normalizeCheckpointMessages,
} from "@/core/messages/merge";
import { getAPIClient } from "../api";

import type { AgentThreadState } from "./types";

const NEW_THREAD_ID = "new";

function historyMessagesFromThread(
  history: Array<{ values?: AgentThreadState }> | undefined,
): Message[] {
  const head = history?.[0]?.values;
  const messages = head?.messages ?? [];
  return normalizeCheckpointMessages(messages);
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
  const isNewThread = !threadId || threadId === NEW_THREAD_ID;
  const [onStreamThreadId, setOnStreamThreadId] = useState<string | undefined>(
    () => (isNewThread ? undefined : threadId),
  );
  const [optimisticMessages, setOptimisticMessages] = useState<Message[]>([]);
  const listeners = useRef({ onCreated, onFinish, onThreadId });
  const pendingNavigationThreadId = useRef<string | null>(null);
  const queryClient = useQueryClient();

  useEffect(() => {
    listeners.current = { onCreated, onFinish, onThreadId };
  }, [onCreated, onFinish, onThreadId]);

  useEffect(() => {
    if (!threadId || threadId === NEW_THREAD_ID) return;
    setOnStreamThreadId(threadId);
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
      pendingNavigationThreadId.current = meta.thread_id;
      listeners.current.onCreated?.({
        thread_id: meta.thread_id,
        run_id: meta.run_id,
      });
    },
    onFinish(state) {
      setOptimisticMessages([]);
      listeners.current.onFinish?.(state);

      const activeThreadId =
        pendingNavigationThreadId.current ??
        onStreamThreadId ??
        (threadId && threadId !== NEW_THREAD_ID ? threadId : null);

      if (activeThreadId) {
        queryClient.invalidateQueries({ queryKey: ["threads"] });
        queryClient.invalidateQueries({ queryKey: ["threads", activeThreadId] });
      }
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

  const historyMessages = historyMessagesFromThread(thread.history);
  const pendingOptimistic = filterConfirmedOptimistic(
    thread.messages,
    optimisticMessages,
  );

  const messages = mergeMessages(
    historyMessages,
    thread.messages,
    pendingOptimistic,
  );

  return {
    ...thread,
    messages,
    sendMessage,
    clearOptimistic: () => setOptimisticMessages([]),
    pendingNavigationThreadId,
  };
}

export { NEW_THREAD_ID };
