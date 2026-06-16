"use client";

import type { Message } from "@langchain/langgraph-sdk";
import { useRouter, useSearchParams } from "next/navigation";
import React, { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";

import { ChatColumnHeader } from "@/components/workspace/ChatColumnHeader";
import { HomePromptInput } from "@/components/workspace/HomePromptInput";
import { MessageList } from "@/components/workspace/MessageList";
import { MessageQueueBar } from "@/components/workspace/MessageQueueBar";
import { StrategyWorkspace } from "@/components/workspace/StrategyWorkspace";
import { useLoginModal } from "@/contexts/LoginModalContext";
import { useAuth } from "@/core/auth/AuthProvider";
import { useAnalyzeStream } from "@/core/chat/useAnalyzeStream";
import { useBacktestStream } from "@/core/chat/useBacktestStream";
import { useSessionState } from "@/core/chat/useSessionState";
import { ShareModal } from "@/components/workspace/ShareModal";
import type { PerformancePoint } from "@/components/workspace/PerformanceChart";
import type { TradeDayGroup } from "@/components/workspace/TradeDetailsPanel";
import type { HoldingDayGroup } from "@/components/workspace/HoldingDetailsPanel";
import type { BacktestMetrics, BacktestResultDetail } from "@/core/chat/types";
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

function NewChatRedirect() {
  const router = useRouter();

  useEffect(() => {
    router.replace("/workspace");
  }, [router]);

  return (
    <div className="flex h-full items-center justify-center text-sm text-gray-400">
      跳转中…
    </div>
  );
}

function ChatPageContent({
  params,
}: {
  params: Promise<{ thread_id: string }>;
}) {
  const { thread_id } = React.use(params);

  if (thread_id === NEW_THREAD_ID) {
    return <NewChatRedirect />;
  }

  return <ChatThreadPage thread_id={thread_id} />;
}

function ChatThreadPage({ thread_id }: { thread_id: string }) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { isAuthenticated } = useAuth();
  const { openLoginModal } = useLoginModal();
  const { data: thread } = useThread(thread_id);
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
  const backtestIdRef = useRef<string | null>(null);
  const [lastBacktestId, setLastBacktestId] = useState<string | null>(null);
  const [streamUrl, setStreamUrl] = useState<string | null>(null);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [logLines, setLogLines] = useState<string[]>([]);
  const [performanceSeries, setPerformanceSeries] = useState<PerformancePoint[]>([]);
  const [tradeGroups, setTradeGroups] = useState<TradeDayGroup[]>([]);
  const [holdingGroups, setHoldingGroups] = useState<HoldingDayGroup[]>([]);
  const [inputPrefill, setInputPrefill] = useState<string | null>(null);
  const [shareOpen, setShareOpen] = useState(false);
  const [shareUrl, setShareUrl] = useState<string | null>(null);
  const [shareCreating, setShareCreating] = useState(false);
  const lastSyncedBlockRef = useRef<string | null>(null);
  const wasLoadingRef = useRef(false);
  const editorVersionRef = useRef(1);
  const initialMessageSentRef = useRef(false);

  const {
    messages,
    isLoading,
    sendMessage,
    values,
    error: streamError,
    stopStream,
    queuePaused,
    queuedMessages,
    removeQueuedMessage,
    updateQueuedMessage,
    moveQueuedMessageUp,
    moveQueuedMessageDown,
    sendQueuedMessageNow,
  } = useThreadStream({
      threadId: thread_id,
      onCreated: () => {},
      onFinish: () => {},
    });

  const latestPythonBlock = useMemo(
    () => extractLatestPythonBlock(messages as Message[]),
    [messages],
  );

  const threadTitle =
    thread?.title ??
    (typeof values?.title === "string" ? values.title : null);

  const showStrategyWorkspace = workspace.isOpen;
  const hasRunResults =
    workspace.runStatus !== "idle" || lastMetrics != null || lastBacktestId != null;

  const strategyPanelTitle =
    threadTitle?.trim() ||
    editorCode.match(/^#\s*(.+)/m)?.[1]?.trim() ||
    "未命名策略";

  const handleOpenStrategyCode = useCallback(() => {
    if (latestPythonBlock) {
      setEditorCode(latestPythonBlock);
      lastSyncedBlockRef.current = latestPythonBlock;
      editorVersionRef.current += 1;
    }
    workspace.openWorkspace();
  }, [latestPythonBlock, workspace]);

  useEffect(() => {
    workspace.closeWorkspace();
  }, [thread_id, workspace.closeWorkspace]);

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

  useEffect(() => {
    backtestIdRef.current = backtestId;
  }, [backtestId]);

  const fetchBacktestDetail = useCallback(async (id: string) => {
    const res = await fetch(`/api/v1/backtest/${id}`, { credentials: "include" });
    if (!res.ok) return;
    const data = (await res.json()) as BacktestResultDetail & {
      performance?: PerformancePoint[];
      trades?: TradeDayGroup[];
      holdings?: HoldingDayGroup[];
    };
    setPerformanceSeries(data.performance ?? []);
    setTradeGroups(data.trades ?? []);
    setHoldingGroups(data.holdings ?? []);
  }, []);

  const { connect, disconnect } = useBacktestStream(streamUrl ?? "", {
    onStarted: (id) => {
      setBacktestId(id);
      setLogLines([]);
      workspace.onRunStarted();
    },
    onProgress: () => {},
    onLogLine: (line) => {
      setLogLines((prev) => [...prev, line]);
    },
    onComplete: (metrics: BacktestMetrics) => {
      const id = backtestIdRef.current;
      if (id) {
        setLastBacktestId(id);
        void fetchBacktestDetail(id);
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
      !isAuthenticated
    ) {
      return;
    }

    initialMessageSentRef.current = true;
    sendMessage(initialMessage);
    router.replace(`/workspace/chats/${thread_id}`);
  }, [
    isAuthenticated,
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

    if (sessionState !== "code_ready" || !editorCode.trim()) {
      return;
    }

    cancelAnalyze();
    setSubmitError(null);
    setLogLines([]);
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
    lastBacktestId,
    lastMetrics,
    openLoginModal,
    startAnalyze,
    thread_id,
  ]);

  const handleAiFix = useCallback(() => {
    const recentErrors = logLines.slice(-8).join("\n");
    setInputPrefill(
      `请根据以下回测日志修复策略代码中的问题：\n\n${recentErrors}\n\n请给出修复后的完整 Python 策略代码。`,
    );
  }, [logLines]);

  const handleShare = useCallback(async () => {
    if (!isAuthenticated) {
      openLoginModal();
      return;
    }

    setShareOpen(true);
    setShareCreating(true);
    setShareUrl(null);

    try {
      const res = await fetch("/api/v1/share", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({
          thread_id,
          title: threadTitle,
          code: editorCode,
          messages: messages.map((m) => ({
            role: m.type,
            content: typeof m.content === "string" ? m.content : JSON.stringify(m.content),
          })),
          metrics: lastMetrics,
        }),
      });
      const data = (await res.json()) as { url?: string };
      if (!res.ok || !data.url) throw new Error("分享失败");
      setShareUrl(data.url);
    } catch {
      setShareUrl(null);
    } finally {
      setShareCreating(false);
    }
  }, [
    editorCode,
    isAuthenticated,
    lastMetrics,
    messages,
    openLoginModal,
    thread_id,
    threadTitle,
  ]);

  const handleSubmitSimulation = useCallback(async () => {
    if (!lastBacktestId || workspace.runStatus !== "done") return;
    try {
      const res = await fetch(`/api/v1/backtest/${lastBacktestId}/simulation`, {
        method: "POST",
        credentials: "include",
      });
      if (!res.ok) throw new Error("提交模拟失败");
      setSubmitError(null);
    } catch (error) {
      const message = error instanceof Error ? error.message : "提交模拟失败";
      setSubmitError(message);
    }
  }, [lastBacktestId, workspace.runStatus]);

  return (
    <div className="flex h-full min-h-0 flex-col bg-white">
      <ChatColumnHeader title={threadTitle} />

      {submitError ? (
        <p className="border-b bg-red-50 px-4 py-2 text-sm text-red-700">
          {submitError}
        </p>
      ) : null}

      {streamError ? (
        <p className="border-b bg-amber-50 px-4 py-2 text-sm text-amber-800">
          对话流异常，队列已暂停。修复后可继续发送，或取消队列中的消息。
        </p>
      ) : null}

      <div className="flex min-h-0 flex-1">
        <div
          className={
            showStrategyWorkspace
              ? "flex min-h-0 min-w-0 w-1/2 shrink-0 flex-col border-r bg-white"
              : "flex min-h-0 min-w-0 flex-1 flex-col bg-white"
          }
        >
          <div className="min-h-0 flex-1 overflow-auto px-[25px]">
            <div className="mx-auto w-full max-w-[420px]">
              <MessageList
                messages={messages}
                isLoading={isLoading}
                threadTitle={threadTitle}
                onOpenCode={handleOpenStrategyCode}
              />
            </div>
          </div>
          <div className="bg-white px-[25px] pb-8 pt-2">
            <div
              className={
                showStrategyWorkspace ? "w-full" : "mx-auto w-full max-w-[720px]"
              }
            >
              <MessageQueueBar
                items={queuedMessages}
                paused={queuePaused}
                onRemove={removeQueuedMessage}
                onMoveUp={moveQueuedMessageUp}
                onMoveDown={moveQueuedMessageDown}
                onEdit={updateQueuedMessage}
                onSendNow={sendQueuedMessageNow}
              />
              <HomePromptInput
                onSend={handleSend}
                onStop={() => void stopStream()}
                prefill={inputPrefill}
                onPrefillApplied={() => setInputPrefill(null)}
                showDisclaimer
                variant="chat"
                isStreaming={isLoading}
                placeholder="请输入您的策略想法 (Shift + Enter换行)"
              />
            </div>
          </div>
        </div>

        {showStrategyWorkspace ? (
          <StrategyWorkspace
            title={strategyPanelTitle}
            onClose={workspace.closeWorkspace}
            activeTab={workspace.activeTab}
            onTabChange={workspace.setActiveTab}
            runStatus={workspace.runStatus}
            hasRunResults={hasRunResults}
            editorCode={editorCode}
            onEditorChange={setEditorCode}
            isGenerating={isLoading}
            editorReadOnly={isLoading || sessionState === "backtesting"}
            sessionState={sessionState}
            jqcliConfigured={jqcliConfigured}
            lastMetrics={lastMetrics}
            isAnalyzing={isAnalyzing}
            logLines={logLines}
            performanceSeries={performanceSeries}
            tradeGroups={tradeGroups}
            holdingGroups={holdingGroups}
            onRunBacktest={() => void handleRunBacktest()}
            onAbortBacktest={handleAbortBacktest}
            onAnalyze={() => void handleRunAnalyze()}
            onAiFix={handleAiFix}
            onSubmitSimulation={() => void handleSubmitSimulation()}
            onShare={() => void handleShare()}
          />
        ) : null}
      </div>

      <ShareModal
        open={shareOpen}
        onClose={() => setShareOpen(false)}
        shareUrl={shareUrl}
        isCreating={shareCreating}
      />
    </div>
  );
}
