"use client";

import { useEffect } from "react";
import { X } from "lucide-react";

import { BacktestButton } from "@/components/workspace/BacktestButton";
import type { BacktestMetrics, SessionState } from "@/core/chat/types";
import type { StrategyTab, RunStatus } from "@/hooks/useStrategyWorkspace";

const ALL_TABS: { id: StrategyTab; label: string }[] = [
  { id: "code", label: "策略代码" },
  { id: "performance", label: "收益概况" },
  { id: "trades", label: "交易详情" },
  { id: "holdings", label: "持仓详情" },
  { id: "logs", label: "运行日志" },
];

const RESULT_TAB_IDS = new Set<StrategyTab>(
  ALL_TABS.filter((tab) => tab.id !== "code").map((tab) => tab.id),
);

interface WorkspaceHeaderProps {
  title: string | null;
  onClose: (() => void) | undefined;
  activeTab: StrategyTab;
  onTabChange: (tab: StrategyTab) => void;
  hasRunResults?: boolean;
  sessionState: SessionState;
  jqcliConfigured: boolean;
  hasEditorCode?: boolean;
  lastMetrics: BacktestMetrics | null;
  runStatus: RunStatus;
  onRunBacktest: () => void;
  onAbortBacktest: () => void;
}

export function WorkspaceHeader({
  title,
  onClose,
  activeTab,
  onTabChange,
  hasRunResults = false,
  sessionState,
  jqcliConfigured,
  hasEditorCode = false,
  onRunBacktest,
  onAbortBacktest,
}: WorkspaceHeaderProps) {
  const visibleTabs = hasRunResults
    ? ALL_TABS
    : ALL_TABS.filter((tab) => tab.id === "code");

  useEffect(() => {
    if (!hasRunResults && RESULT_TAB_IDS.has(activeTab)) {
      onTabChange("code");
    }
  }, [activeTab, hasRunResults, onTabChange]);

  return (
    <div className="flex flex-col border-b bg-white">
      {title || onClose ? (
        <div className="flex items-center gap-2 border-b border-gray-100 px-3 py-2">
          {onClose ? (
            <button
              type="button"
              onClick={onClose}
              className="rounded-md p-1.5 text-gray-500 hover:bg-gray-100"
              aria-label="关闭策略面板"
            >
              <X className="size-4" />
            </button>
          ) : null}
          {title ? (
            <h2 className="min-w-0 truncate text-sm font-medium text-gray-900">
              {title}
            </h2>
          ) : null}
        </div>
      ) : null}
      <div className="flex items-center justify-between gap-2 px-3 py-0">
        <nav
          className="flex min-w-0 flex-wrap gap-4 text-sm"
          aria-label="策略工作区"
        >
          {visibleTabs.map((tab) => (
            <button
              key={tab.id}
              type="button"
              onClick={() => onTabChange(tab.id)}
              className={
                activeTab === tab.id
                  ? "border-b-2 border-red-500 py-3 font-medium text-gray-900"
                  : "border-b-2 border-transparent py-3 text-gray-500 hover:text-gray-900"
              }
            >
              {tab.label}
            </button>
          ))}
        </nav>
        <div className="flex shrink-0 items-center gap-2 py-2">
          <BacktestButton
            state={sessionState}
            jqcliConfigured={jqcliConfigured}
            hasEditorCode={hasEditorCode}
            onRun={onRunBacktest}
            onAbort={onAbortBacktest}
            runLabel="运行策略"
          />
        </div>
      </div>
    </div>
  );
}
