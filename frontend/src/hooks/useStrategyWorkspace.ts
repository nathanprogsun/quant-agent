"use client";

import { useCallback, useState } from "react";

export type StrategyTab = "code" | "performance" | "trades" | "holdings" | "logs";

export type RunStatus = "idle" | "running" | "done" | "failed";

export function useStrategyWorkspace() {
  const [activeTab, setActiveTab] = useState<StrategyTab>("code");
  const [runStatus, setRunStatus] = useState<RunStatus>("idle");

  const openCodeTab = useCallback(() => {
    setActiveTab("code");
  }, []);

  const onRunStarted = useCallback(() => {
    setRunStatus("running");
  }, []);

  const onRunComplete = useCallback(() => {
    setRunStatus("done");
  }, []);

  const onRunFailed = useCallback(() => {
    setRunStatus("failed");
  }, []);

  const resetRunStatus = useCallback(() => {
    setRunStatus("idle");
  }, []);

  return {
    activeTab,
    setActiveTab,
    runStatus,
    setRunStatus,
    openCodeTab,
    onRunStarted,
    onRunComplete,
    onRunFailed,
    resetRunStatus,
  };
}
