"use client";

import { useCallback, useEffect, useState } from "react";

export type StrategyTab = "code" | "performance" | "trades" | "holdings" | "logs";

export type RunStatus = "idle" | "running" | "done" | "failed";

export const SPLIT_RATIO_DEFAULT = 0.65;
export const SPLIT_RATIO_MIN = 0.2;
export const SPLIT_RATIO_MAX = 0.8;
export const SPLIT_RATIO_STORAGE_KEY = "quant-agent:split-ratio";

function clampSplitRatio(value: number): number {
  if (!Number.isFinite(value)) return SPLIT_RATIO_DEFAULT;
  return Math.min(SPLIT_RATIO_MAX, Math.max(SPLIT_RATIO_MIN, value));
}

function readPersistedSplitRatio(): number {
  if (typeof window === "undefined") return SPLIT_RATIO_DEFAULT;
  try {
    const raw = window.localStorage.getItem(SPLIT_RATIO_STORAGE_KEY);
    if (!raw) return SPLIT_RATIO_DEFAULT;
    const parsed = Number.parseFloat(raw);
    return clampSplitRatio(parsed);
  } catch {
    return SPLIT_RATIO_DEFAULT;
  }
}

export function useStrategyWorkspace() {
  const [isOpen, setIsOpen] = useState(false);
  const [activeTab, setActiveTab] = useState<StrategyTab>("code");
  const [runStatus, setRunStatus] = useState<RunStatus>("idle");
  const [splitRatio, setSplitRatioState] = useState<number>(SPLIT_RATIO_DEFAULT);

  useEffect(() => {
    setSplitRatioState(readPersistedSplitRatio());
  }, []);

  const setSplitRatio = useCallback((next: number) => {
    const clamped = clampSplitRatio(next);
    setSplitRatioState(clamped);
    if (typeof window !== "undefined") {
      try {
        window.localStorage.setItem(SPLIT_RATIO_STORAGE_KEY, String(clamped));
      } catch {
        // ignore storage errors (e.g. private mode, quota)
      }
    }
  }, []);

  const resetSplitRatio = useCallback(() => {
    setSplitRatio(SPLIT_RATIO_DEFAULT);
  }, [setSplitRatio]);

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
    splitRatio,
    setSplitRatio,
    resetSplitRatio,
  };
}
