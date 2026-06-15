"use client";

import { BacktestButton } from "@/components/workspace/BacktestButton";
import { AnalyzeButton } from "@/components/workspace/AnalyzeButton";
import type { BacktestMetrics, SessionState } from "@/core/chat/types";
import type { StrategyTab } from "@/hooks/useStrategyWorkspace";

const TABS: { id: StrategyTab; label: string }[] = [
  { id: "code", label: "策略代码" },
  { id: "performance", label: "收益概况" },
  { id: "trades", label: "交易详情" },
  { id: "holdings", label: "持仓详情" },
  { id: "logs", label: "运行日志" },
];

interface WorkspaceHeaderProps {
  activeTab: StrategyTab;
  onTabChange: (tab: StrategyTab) => void;
  sessionState: SessionState;
  jqcliConfigured: boolean;
  lastMetrics: BacktestMetrics | null;
  isAnalyzing: boolean;
  onRunBacktest: () => void;
  onAbortBacktest: () => void;
  onAnalyze: () => void;
}

export function WorkspaceHeader({
  activeTab,
  onTabChange,
  sessionState,
  jqcliConfigured,
  lastMetrics,
  isAnalyzing,
  onRunBacktest,
  onAbortBacktest,
  onAnalyze,
}: WorkspaceHeaderProps) {
  return (
    <div className="flex flex-col border-b bg-white">
      <div className="flex items-center justify-between gap-2 px-3 py-2">
        <nav className="flex flex-wrap gap-1" aria-label="策略工作区">
          {TABS.map((tab) => (
            <button
              key={tab.id}
              type="button"
              onClick={() => onTabChange(tab.id)}
              className={
                activeTab === tab.id
                  ? "rounded-md bg-gray-100 px-3 py-1.5 text-sm font-medium text-gray-900"
                  : "rounded-md px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-50"
              }
            >
              {tab.label}
            </button>
          ))}
        </nav>
        <div className="flex shrink-0 items-center gap-2">
          <BacktestButton
            state={sessionState}
            jqcliConfigured={jqcliConfigured}
            onRun={onRunBacktest}
            onAbort={onAbortBacktest}
            runLabel="运行策略"
          />
          <AnalyzeButton
            state={sessionState}
            lastMetricsAvailable={lastMetrics != null}
            isAnalyzing={isAnalyzing}
            onAnalyze={onAnalyze}
          />
        </div>
      </div>
    </div>
  );
}
