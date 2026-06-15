"use client";

import type { Message } from "@langchain/langgraph-sdk";
import { useRouter, useSearchParams } from "next/navigation";
import React, { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";

import { ChatWorkspaceHeader } from "@/components/workspace/ChatWorkspaceHeader";
import { InputBox } from "@/components/workspace/InputBox";
import { MessageList } from "@/components/workspace/MessageList";
import { StrategyWorkspace } from "@/components/workspace/StrategyWorkspace";
import { useLoginModal } from "@/contexts/LoginModalContext";
import { useAuth } from "@/core/auth/AuthProvider";
import { useAnalyzeStream } from "@/core/chat/useAnalyzeStream";
import { useBacktestStream } from "@/core/chat/useBacktestStream";
import { useSessionState } from "@/core/chat/useSessionState";
import type { BacktestMetrics } from "@/core/chat/types";
import {
  extractLatestPythonBlock,
  shouldSyncEditorCode,
} from "@/core/messages/pythonBlocks";
import { useStrategyWorkspace } from "@/hooks/useStrategyWorkspace";
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
  return (
    <Suspense fallback={<div className="p-4 text-gray-500">加载中…</div>}>
      <ChatPageContent params={params} />
    </Suspense>
  );
}

function ChatPageContent({
  params,
}: {
  params: Promise<{ thread_id: string }>;
}) {
  const { thread_id } = React.use(params);
  const router = useRouter();
  const searchParams = useSearchParams();
  const { isAuthenticated } = useAuth();
  const { openLoginModal } = useLoginModal();
  const isNewThread = thread_id === NEW_THREAD_ID;
  const { data: thread } = useThread(isNewThread ? null : thread_id);

  const workspace = useStrategyWorkspace();

  const {
    state: sessionState,
    lastMetrics,
    generate,
    codeComplete,
    startBacktest,
    backtestComplete,
    backtestFailed,
    analysisComplete,
    reset,
  } = useSessionState();

  const [editorCode, setEditorCode] = useState("");
  const [jqcliConfigured, setJqcliConfigured] = useState(false);
  const [backtestId, setBacktestId] = useState<string | null>(null);
  const [lastBacktestId, setLastBacktestId] = useState<string | null>(null);
  const [streamUrl, setStreamUrl] = useState<string | null>(null);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const lastSyncedBlockRef = useRef<string | null>(null);
  const wasLoadingRef = useRef(false);
  const editorVersionRef = useRef(1);
  const initialMessageSentRef = useRef(false);

  const { messages, isLoading, sendMessage, pendingNavigationThreadId, values } =
    useThreadStream({
      threadId: isNewThread ? null : thread_id,
      onCreated: () => {},
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

  const showStrategyWorkspace = Boolean(
    editorCode.trim() ||
      latestPythonBlock ||
      sessionState === "code_ready" ||
      sessionState === "backtesting" ||
      sessionState === "analyzed",
  );

  const threadTitle =
    thread?.title ??
    (typeof values?.title === "string" ? values.title : null);

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
      workspace.onRunStarted();
    },
    onProgress: () => {},
    onComplete: (metrics: BacktestMetrics) => {
      if (backtestId) {
        setLastBacktestId(backtestId);
      }
      backtestComplete(metrics);
      workspace.onRunComplete();
      setStreamUrl(null);
      setBacktestId(null);
    },
    onFailed: () => {
      backtestFailed();
      workspace.onRunFailed();
      setStreamUrl(null);
      setBacktestId(null);
    },
    onAborted: () => {
      backtestFailed();
      workspace.resetRunStatus();
      setStreamUrl(null);
      setBacktestId(null);
    },
  });

  const { startAnalyze, cancelAnalyze } = useAnalyzeStream();

  useEffect(() => {
    if (!streamUrl) return;
    connect();
    return () => {
      disconnect();
    };
  }, [streamUrl, connect, disconnect]);

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

  useEffect(() => {
    const initialMessage = searchParams.get("initialMessage");
    if (
      !initialMessage ||
      initialMessageSentRef.current ||
      isNewThread ||
      !isAuthenticated
    ) {
      return;
    }

    initialMessageSentRef.current = true;
    sendMessage(initialMessage);
    router.replace(`/workspace/chats/${thread_id}`);
  }, [
    isAuthenticated,
    isNewThread,
    router,
    searchParams,
    sendMessage,
    thread_id,
  ]);

  const handleSend = useCallback(
    (content: string) => {
      if (!isAuthenticated) {
        openLoginModal();
        return;
      }
      sendMessage(content);
    },
    [isAuthenticated, openLoginModal, sendMessage],
  );

  const handleRunBacktest = useCallback(async () => {
    if (!isAuthenticated) {
      openLoginModal();
      return;
    }

    if (isNewThread || sessionState !== "code_ready" || !editorCode.trim()) {
      return;
    }

    cancelAnalyze();
    setSubmitError(null);
    startBacktest();
    workspace.onRunStarted();

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
      setLastBacktestId(data.backtest_id);
      setStreamUrl(`/api/v1/backtest/${data.backtest_id}/stream`);
    } catch (error) {
      const message = error instanceof Error ? error.message : "回测提交失败";
      setSubmitError(message);
      backtestFailed();
      workspace.onRunFailed();
    }
  }, [
    cancelAnalyze,
    editorCode,
    isAuthenticated,
    isNewThread,
    openLoginModal,
    sessionState,
    startBacktest,
    thread_id,
    workspace,
    backtestFailed,
  ]);

  const handleAbortBacktest = useCallback(() => {
    disconnect();
    setStreamUrl(null);
    setBacktestId(null);
    workspace.resetRunStatus();
    backtestFailed();
  }, [backtestFailed, disconnect, workspace]);

  const handleRunAnalyze = useCallback(async () => {
    if (!isAuthenticated) {
      openLoginModal();
      return;
    }

    if (
      isNewThread ||
      !lastMetrics ||
      !lastBacktestId ||
      isAnalyzing ||
      !editorCode.trim()
    ) {
      return;
    }

    setSubmitError(null);
    setIsAnalyzing(true);

    try {
      await startAnalyze(
        {
          thread_id,
          backtest_id: lastBacktestId,
          code: editorCode,
          metrics: lastMetrics as Record<string, unknown>,
        },
        {
          onDelta: () => {},
          onDone: () => {
            analysisComplete();
            setIsAnalyzing(false);
          },
          onError: () => {
            setIsAnalyzing(false);
          },
        },
      );
    } catch {
      setIsAnalyzing(false);
    }
  }, [
    analysisComplete,
    editorCode,
    isAnalyzing,
    isAuthenticated,
    isNewThread,
    lastBacktestId,
    lastMetrics,
    openLoginModal,
    startAnalyze,
    thread_id,
  ]);

  return (
    <div className="flex h-full min-h-0 flex-col">
      <ChatWorkspaceHeader threadId={thread_id} title={threadTitle} />

      {submitError ? (
        <p className="border-b bg-red-50 px-4 py-2 text-sm text-red-700">
          {submitError}
        </p>
      ) : null}

      <div className="flex min-h-0 flex-1">
        <div
          className={
            showStrategyWorkspace
              ? "flex min-w-0 flex-1 flex-col border-r"
              : "flex min-w-0 flex-1 flex-col"
          }
        >
          <div className="min-h-0 flex-1 overflow-auto">
            <MessageList
              messages={messages}
              isLoading={isLoading}
              threadTitle={threadTitle}
              onOpenCode={workspace.openCodeTab}
            />
          </div>
          <InputBox onSend={handleSend} disabled={isLoading} />
        </div>

        {showStrategyWorkspace ? (
          <StrategyWorkspace
            activeTab={workspace.activeTab}
            onTabChange={workspace.setActiveTab}
            editorCode={editorCode}
            onEditorChange={setEditorCode}
            isGenerating={isLoading}
            editorReadOnly={isLoading || sessionState === "backtesting"}
            sessionState={sessionState}
            jqcliConfigured={jqcliConfigured}
            lastMetrics={lastMetrics}
            isAnalyzing={isAnalyzing}
            onRunBacktest={() => void handleRunBacktest()}
            onAbortBacktest={handleAbortBacktest}
            onAnalyze={() => void handleRunAnalyze()}
          />
        ) : null}
      </div>
    </div>
  );
}
