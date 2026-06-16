"use client";

import { useCallback, useState } from "react";

export type StrategyTab = "code" | "performance" | "trades" | "holdings" | "logs";

export type RunStatus = "idle" | "running" | "done" | "failed";

export function useStrategyWorkspace() {
  const [isOpen, setIsOpen] = useState(false);
  const [activeTab, setActiveTab] = useState<StrategyTab>("code");
  const [runStatus, setRunStatus] = useState<RunStatus>("idle");

  const openWorkspace = useCallback(() => {
    setIsOpen(true);
    setActiveTab("code");
  }, []);

  const closeWorkspace = useCallback(() => {
    setIsOpen(false);
  }, []);

  const onRunStarted = useCallback(() => {
    setIsOpen(true);
    setRunStatus("running");
    setActiveTab("logs");
  }, []);

  const onRunComplete = useCallback(() => {
    setRunStatus("done");
    setActiveTab("performance");
  }, []);

  const onRunFailed = useCallback(() => {
    setRunStatus("failed");
    setActiveTab("logs");
  }, []);

  const resetRunStatus = useCallback(() => {
    setRunStatus("idle");
  }, []);

  return {
    isOpen,
    activeTab,
    setActiveTab,
    runStatus,
    setRunStatus,
    openWorkspace,
    closeWorkspace,
    onRunStarted,
    onRunComplete,
    onRunFailed,
    resetRunStatus,
  };
}
