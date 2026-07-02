import type { Message } from "@langchain/langgraph-sdk";
import { useStream } from "@langchain/langgraph-sdk/react";
import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  filterConfirmedOptimistic,
  mergeMessages,
  normalizeCheckpointMessages,
} from "@/core/messages/merge";
import { getAPIClient } from "../api";

import type { AgentThreadState } from "./types";
import {
  extractHumanTextFromSubmitValues,
  humanMessageFromContent,
} from "./messageQueue";

const NEW_THREAD_ID = "new";

export interface QueuedMessageItem {
  id: string;
  content: string;
}

function historyMessagesFromThread(
  history: Array<{ values?: AgentThreadState }> | undefined,
): Message[] {
  const head = history?.[0]?.values;
  const messages = head?.messages ?? [];
  return normalizeCheckpointMessages(messages);
}

function queueItemsFromSdkEntries(
  entries: ReadonlyArray<{
    id: string;
    values: Partial<AgentThreadState> | null | undefined;
  }> | undefined,
): QueuedMessageItem[] {
  if (!entries?.length) return [];
  return entries.map((entry) => ({
    id: entry.id,
    content: extractHumanTextFromSubmitValues(entry.values),
  }));
}

type ThreadQueueApi = {
  entries: ReadonlyArray<{
    id: string;
    values: Partial<AgentThreadState> | null | undefined;
  }>;
  cancel: (id: string) => Promise<void>;
  clear: () => Promise<void>;
};

function getThreadQueueApi(thread: unknown): ThreadQueueApi | undefined {
  const queue = (thread as { queue?: ThreadQueueApi }).queue;
  if (!queue?.cancel || !queue?.clear) return undefined;
  return queue;
}

function createLocalQueueId(): string {
  return `local-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

// ── Thread Stream Options ───────────────────────────────────────────────────

export interface ThreadStreamOptions {
  threadId?: string | null;
  assistantId?: string;
  onThreadId?: (threadId: string) => void;
  onCreated?: (meta: { thread_id: string; run_id: string }) => void;
  onFinish?: (state: { values: AgentThreadState }) => void;
}

export interface StoppedSnapshot {
  messages: Message[];
  capturedAt: number;
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
  const [queuePaused, setQueuePaused] = useState(false);
  const [queueOrder, setQueueOrder] = useState<string[]>([]);
  const [localQueue, setLocalQueue] = useState<QueuedMessageItem[]>([]);
  const listeners = useRef({ onCreated, onFinish, onThreadId });
  const pendingNavigationThreadId = useRef<string | null>(null);
  const queryClient = useQueryClient();

  useEffect(() => {
    listeners.current = { onCreated, onFinish, onThreadId };
  }, [onCreated, onFinish, onThreadId]);

  useEffect(() => {
    if (!threadId || threadId === NEW_THREAD_ID) return;
    setOnStreamThreadId(threadId);
    setQueueOrder([]);
    setQueuePaused(false);
    setLocalQueue([]);
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
      const finishedMessages = normalizeCheckpointMessages(
        (state.values?.messages as Message[] | undefined) ?? [],
      );
      setOptimisticMessages((prev) =>
        filterConfirmedOptimistic(finishedMessages, prev),
      );
      setQueuePaused(false);
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
    onError() {
      setQueuePaused(true);
    },
  });

  const queueApi = getThreadQueueApi(thread);
  const hasSdkQueue = Boolean(queueApi);
  const sdkQueueEntries = queueApi?.entries;

  const sdkQueueItems = useMemo(
    () => queueItemsFromSdkEntries(sdkQueueEntries),
    [sdkQueueEntries],
  );

  const baseQueueItems = hasSdkQueue ? sdkQueueItems : localQueue;

  useEffect(() => {
    const ids = baseQueueItems.map((item) => item.id);
    setQueueOrder((prev) => {
      if (prev.length === 0) return ids;
      const kept = prev.filter((id) => ids.includes(id));
      const appended = ids.filter((id) => !kept.includes(id));
      return [...kept, ...appended];
    });
  }, [baseQueueItems]);

  const orderedQueueItems = useMemo(() => {
    if (queueOrder.length === 0) return baseQueueItems;
    const byId = new Map(baseQueueItems.map((item) => [item.id, item]));
    const ordered = queueOrder
      .map((id) => byId.get(id))
      .filter((item): item is QueuedMessageItem => Boolean(item));
    const trailing = baseQueueItems.filter((item) => !queueOrder.includes(item.id));
    return [...ordered, ...trailing];
  }, [baseQueueItems, queueOrder]);

  const submitHumanMessage = useCallback(
    (content: string, options?: { interrupt?: boolean }) => {
      return thread.submit(
        { messages: [{ type: "human", content }] },
        options?.interrupt ? { multitaskStrategy: "rollback" } : undefined,
      );
    },
    [thread],
  );

  useEffect(() => {
    if (hasSdkQueue || queuePaused || thread.isLoading || localQueue.length === 0) {
      return;
    }

    const [next, ...rest] = localQueue;
    setLocalQueue(rest);
    void submitHumanMessage(next.content);
  }, [
    hasSdkQueue,
    localQueue,
    queuePaused,
    submitHumanMessage,
    thread.isLoading,
  ]);

  const sendMessage = useCallback(
    (content: string) => {
      const trimmed = content.trim();
      if (!trimmed) return;

      if (queuePaused) {
        setQueuePaused(false);
      }

      setOptimisticMessages((prev) => [...prev, humanMessageFromContent(trimmed)]);

      if (thread.isLoading && !hasSdkQueue) {
        setLocalQueue((prev) => [
          ...prev,
          { id: createLocalQueueId(), content: trimmed },
        ]);
        return;
      }

      void submitHumanMessage(trimmed);
    },
    [hasSdkQueue, queuePaused, submitHumanMessage, thread.isLoading],
  );

  const lastMessagesSnapshotRef = useRef<StoppedSnapshot | null>(null);
  const [lastMessagesSnapshot, setLastMessagesSnapshot] =
    useState<StoppedSnapshot | null>(null);

  // Keep a snapshot of the latest non-empty messages so we can fall back
  // to them if `thread.stop()` (or any other code path) clears the streaming
  // state and the history endpoint hasn't caught up yet.
  useEffect(() => {
    if (thread.messages.length > 0) {
      const snapshot = {
        messages: thread.messages,
        capturedAt: Date.now(),
      };
      lastMessagesSnapshotRef.current = snapshot;
      setLastMessagesSnapshot(snapshot);
    }
  }, [thread.messages]);

  const stopStream = useCallback(async () => {
    void lastMessagesSnapshotRef.current;
    await thread.stop();
  }, [thread]);

  const removeQueuedMessage = useCallback(
    async (id: string) => {
      if (hasSdkQueue && queueApi) {
        await queueApi.cancel(id);
      } else {
        setLocalQueue((prev) => prev.filter((entry) => entry.id !== id));
      }
      setQueueOrder((prev) => prev.filter((entryId) => entryId !== id));
    },
    [hasSdkQueue, queueApi],
  );

  const updateQueuedMessage = useCallback(
    async (id: string, content: string) => {
      const trimmed = content.trim();
      if (!trimmed) return;

      if (hasSdkQueue && queueApi) {
        await queueApi.cancel(id);
        setQueueOrder((prev) => prev.filter((entryId) => entryId !== id));
        void submitHumanMessage(trimmed);
        return;
      }

      setLocalQueue((prev) =>
        prev.map((item) =>
          item.id === id ? { ...item, content: trimmed } : item,
        ),
      );
    },
    [hasSdkQueue, queueApi, submitHumanMessage],
  );

  const moveQueuedMessage = useCallback(
    async (id: string, direction: "up" | "down") => {
      const index = queueOrder.indexOf(id);
      if (index < 0) return;
      const target = direction === "up" ? index - 1 : index + 1;
      if (target < 0 || target >= queueOrder.length) return;

      const nextOrder = [...queueOrder];
      const [item] = nextOrder.splice(index, 1);
      nextOrder.splice(target, 0, item);
      setQueueOrder(nextOrder);

      if (!hasSdkQueue) {
        setLocalQueue((prev) => {
          const byId = new Map(prev.map((entry) => [entry.id, entry]));
          return nextOrder
            .map((entryId) => byId.get(entryId))
            .filter((entry): entry is QueuedMessageItem => Boolean(entry));
        });
        return;
      }

      if (!queueApi) return;

      const orderedContents = nextOrder
        .map((entryId) => baseQueueItems.find((item) => item.id === entryId))
        .filter((item): item is QueuedMessageItem => Boolean(item))
        .map((item) => item.content);

      await queueApi.clear();
      for (const text of orderedContents) {
        void submitHumanMessage(text);
      }
    },
    [baseQueueItems, hasSdkQueue, queueApi, queueOrder, submitHumanMessage],
  );

  const sendQueuedMessageNow = useCallback(
    async (id: string) => {
      const item = baseQueueItems.find((entry) => entry.id === id);
      if (!item) return;

      if (hasSdkQueue && queueApi) {
        await queueApi.cancel(id);
      } else {
        setLocalQueue((prev) => prev.filter((entry) => entry.id !== id));
      }

      setQueueOrder((prev) => prev.filter((entryId) => entryId !== id));
      await thread.stop();
      await submitHumanMessage(item.content, { interrupt: true });
    },
    [baseQueueItems, hasSdkQueue, queueApi, submitHumanMessage, thread],
  );

  const historyMessages = historyMessagesFromThread(thread.history);
  const pendingOptimistic = filterConfirmedOptimistic(
    thread.messages,
    optimisticMessages,
  );

  // If both the SDK stream and the history endpoint are empty
  // (e.g. right after `stopStream` before the checkpointer finishes
  // saving), fall back to a snapshot we captured during the latest
  // non-empty stream so the user keeps seeing what was generated.
  const liveMessages = mergeMessages(
    historyMessages,
    thread.messages,
    pendingOptimistic,
  );
  const messages =
    liveMessages.length > 0
      ? liveMessages
      : lastMessagesSnapshot?.messages ?? liveMessages;

  return {
    ...thread,
    messages,
    sendMessage,
    stopStream,
    queuePaused,
    queuedMessages: orderedQueueItems,
    removeQueuedMessage,
    updateQueuedMessage,
    moveQueuedMessageUp: (id: string) => moveQueuedMessage(id, "up"),
    moveQueuedMessageDown: (id: string) => moveQueuedMessage(id, "down"),
    sendQueuedMessageNow,
    clearOptimistic: () => setOptimisticMessages([]),
    pendingNavigationThreadId,
  };
}

export { NEW_THREAD_ID };
