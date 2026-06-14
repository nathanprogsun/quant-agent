"use client";

import type { Message } from "@langchain/langgraph-sdk";
import { useRouter } from "next/navigation";
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { ChatWorkspaceHeader } from "@/components/workspace/ChatWorkspaceHeader";
import { InputBox } from "@/components/workspace/InputBox";
import { MessageList } from "@/components/workspace/MessageList";
import { StrategyEditor } from "@/components/workspace/StrategyEditor";
import {
  WorkspaceDock,
  type DockBacktestView,
} from "@/components/workspace/WorkspaceDock";
import {
  extractLatestPythonBlock,
  shouldSyncEditorCode,
} from "@/core/messages/pythonBlocks";
import { useBacktestStream } from "@/core/chat/useBacktestStream";
import { useSessionState } from "@/core/chat/useSessionState";
import type { BacktestMetrics } from "@/core/chat/types";
import { useThread } from "@/hooks/useThreads";
import { NEW_THREAD_ID, useThreadStream } from "@/core/threads/hooks";

const DEFAULT_BACKTEST_PARAMS = {
  start_date: "2020-01-01",
  end_date: "2024-12-31",
  initial_capital: 100000,
  frequency: "day",
  benchmark: "000300.XSHG",
};

export default function ChatPage({
  params,
}: {
  params: Promise<{ thread_id: string }>;
}) {
  const { thread_id } = React.use(params);
  const router = useRouter();
  const isNewThread = thread_id === NEW_THREAD_ID;
  const { data: thread } = useThread(isNewThread ? null : thread_id);

  const {
    state: sessionState,
    generate,
    codeComplete,
    startBacktest,
    backtestComplete,
    backtestFailed,
    reset,
  } = useSessionState();

  const [editorCode, setEditorCode] = useState("");
  const [jqcliConfigured, setJqcliConfigured] = useState(false);
  const [backtestId, setBacktestId] = useState<string | null>(null);
  const [streamUrl, setStreamUrl] = useState<string | null>(null);
  const [dockBacktest, setDockBacktest] = useState<DockBacktestView>({
    kind: "hidden",
  });
  const [submitError, setSubmitError] = useState<string | null>(null);
  const lastSyncedBlockRef = useRef<string | null>(null);
  const wasLoadingRef = useRef(false);
  const editorVersionRef = useRef(1);

  const { messages, isLoading, sendMessage, pendingNavigationThreadId, values } =
    useThreadStream({
      threadId: isNewThread ? null : thread_id,
      onCreated: () => {
        // Defer URL update until the run finishes so history/checkpoint stay in sync.
      },
      onFinish: () => {
        const nextThreadId = pendingNavigationThreadId.current;
        if (isNewThread && nextThreadId) {
          router.replace(`/workspace/chats/${nextThreadId}`);
        }
      },
    });

  const latestPythonBlock = useMemo(
    () => extractLatestPythonBlock(messages as Message[]),
    [messages],
  );

  const showStrategyEditor = Boolean(
    editorCode.trim() ||
      latestPythonBlock ||
      sessionState === "code_ready" ||
      sessionState === "backtesting" ||
      sessionState === "analyzed",
  );

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const res = await fetch("/api/v1/backtest/auth-check");
        if (!res.ok) return;
        const data = (await res.json()) as { configured?: boolean };
        if (!cancelled) {
          setJqcliConfigured(Boolean(data.configured));
        }
      } catch {
        if (!cancelled) {
          setJqcliConfigured(false);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const { connect, disconnect } = useBacktestStream(streamUrl ?? "", {
    onStarted: (id) => {
      setBacktestId(id);
      setDockBacktest({
        kind: "progress",
        status: "running",
        message: "回测已开始...",
      });
    },
    onProgress: (message) => {
      setDockBacktest({
        kind: "progress",
        status: "running",
        message,
      });
    },
    onComplete: (metrics: BacktestMetrics) => {
      setDockBacktest({
        kind: "progress",
        status: "done",
        metrics,
      });
      backtestComplete(metrics);
      setStreamUrl(null);
      setBacktestId(null);
    },
    onFailed: (error) => {
      setDockBacktest({
        kind: "progress",
        status: "failed",
        error,
      });
      backtestFailed();
      setStreamUrl(null);
      setBacktestId(null);
    },
    onAborted: () => {
      setDockBacktest({ kind: "hidden" });
      backtestFailed();
      setStreamUrl(null);
      setBacktestId(null);
    },
  });

  useEffect(() => {
    if (!streamUrl) return;
    connect();
    return () => {
      disconnect();
    };
  }, [streamUrl, connect, disconnect]);

  useEffect(() => {
    if (sessionState !== "backtesting" && dockBacktest.kind === "progress") {
      if (dockBacktest.status === "running") {
        setDockBacktest({ kind: "hidden" });
      }
    }
  }, [sessionState, dockBacktest]);

  useEffect(() => {
    if (isLoading && !wasLoadingRef.current) {
      generate();
    }

    if (!isLoading && wasLoadingRef.current) {
      if (latestPythonBlock) {
        codeComplete();
      } else {
        reset();
      }
    }

    wasLoadingRef.current = isLoading;
  }, [isLoading, latestPythonBlock, generate, codeComplete, reset]);

  useEffect(() => {
    if (
      shouldSyncEditorCode(latestPythonBlock, lastSyncedBlockRef.current) &&
      latestPythonBlock
    ) {
      setEditorCode(latestPythonBlock);
      lastSyncedBlockRef.current = latestPythonBlock;
      editorVersionRef.current += 1;
    }
  }, [latestPythonBlock]);

  const handleRunBacktest = useCallback(async () => {
    if (isNewThread || sessionState !== "code_ready" || !editorCode.trim()) {
      return;
    }

    setSubmitError(null);
    startBacktest();
    setDockBacktest({
      kind: "progress",
      status: "pending",
      message: "正在提交回测...",
    });

    try {
      const res = await fetch("/api/v1/backtest", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          code: editorCode,
          thread_id,
          version: editorVersionRef.current,
          params: DEFAULT_BACKTEST_PARAMS,
        }),
      });

      const data = (await res.json()) as { backtest_id?: string; message?: string };
      if (!res.ok || !data.backtest_id) {
        throw new Error(data.message ?? "回测提交失败");
      }

      setBacktestId(data.backtest_id);
      setStreamUrl(`/api/v1/backtest/${data.backtest_id}/stream`);
    } catch (error) {
      const message = error instanceof Error ? error.message : "回测提交失败";
      setSubmitError(message);
      setDockBacktest({
        kind: "progress",
        status: "failed",
        error: message,
      });
      backtestFailed();
    }
  }, [editorCode, isNewThread, sessionState, startBacktest, thread_id]);

  const handleAbortBacktest = useCallback(() => {
    disconnect();
    setStreamUrl(null);
    setBacktestId(null);
    setDockBacktest({ kind: "hidden" });
    backtestFailed();
  }, [backtestFailed, disconnect]);

  return (
    <div className="flex h-full min-h-0 flex-col">
      <ChatWorkspaceHeader
        threadId={thread_id}
        title={
          thread?.title ??
          (typeof values?.title === "string" ? values.title : null)
        }
        sessionState={sessionState}
        jqcliConfigured={jqcliConfigured}
        onRunBacktest={() => void handleRunBacktest()}
        onAbortBacktest={handleAbortBacktest}
      />

      {submitError ? (
        <p className="border-b bg-red-50 px-4 py-2 text-sm text-red-700">{submitError}</p>
      ) : null}

      <div
        className={
          showStrategyEditor
            ? "grid min-h-0 flex-1 grid-cols-[42fr_58fr] grid-rows-[minmax(0,1fr)_auto_auto]"
            : "grid min-h-0 flex-1 grid-rows-[minmax(0,1fr)_auto_auto]"
        }
      >
        <div
          className={
            showStrategyEditor
              ? "flex min-h-0 flex-col border-r"
              : "flex min-h-0 flex-col"
          }
        >
          <div className="min-h-0 flex-1 overflow-auto">
            <MessageList messages={messages} isLoading={isLoading} />
          </div>
        </div>

        {showStrategyEditor ? (
          <StrategyEditor
            className="min-h-[360px]"
            code={editorCode}
            onChange={setEditorCode}
            isGenerating={isLoading}
            readOnly={isLoading || sessionState === "backtesting"}
          />
        ) : null}

        <WorkspaceDock
          className={showStrategyEditor ? "col-span-2" : undefined}
          backtest={dockBacktest}
        />

        <div className={showStrategyEditor ? "border-r" : undefined}>
          <InputBox onSend={sendMessage} disabled={isLoading} />
        </div>
        {showStrategyEditor ? (
          <div aria-hidden className="bg-[#1e1e1e]" />
        ) : null}
      </div>
    </div>
  );
}
