"use client";

import { RunLogPanel } from "@/components/workspace/RunLogPanel";
import { PerformancePanel } from "@/components/workspace/PerformancePanel";
import { TradeDetailsPanel, type TradeDayGroup } from "@/components/workspace/TradeDetailsPanel";
import {
  HoldingDetailsPanel,
  type HoldingDayGroup,
} from "@/components/workspace/HoldingDetailsPanel";
import { WorkspaceHeader } from "@/components/workspace/WorkspaceHeader";
import { StrategyEditor } from "@/components/workspace/StrategyEditor";
import type { BacktestMetrics, SessionState } from "@/core/chat/types";
import type { PerformancePoint } from "@/components/workspace/PerformanceChart";
import type { StrategyTab, RunStatus } from "@/hooks/useStrategyWorkspace";

interface StrategyWorkspaceProps {
  activeTab: StrategyTab;
  onTabChange: (tab: StrategyTab) => void;
  runStatus: RunStatus;
  editorCode: string;
  onEditorChange: (code: string) => void;
  isGenerating: boolean;
  editorReadOnly: boolean;
  sessionState: SessionState;
  jqcliConfigured: boolean;
  lastMetrics: BacktestMetrics | null;
  isAnalyzing: boolean;
  logLines: string[];
  performanceSeries: PerformancePoint[];
  tradeGroups: TradeDayGroup[];
  holdingGroups: HoldingDayGroup[];
  onRunBacktest: () => void;
  onAbortBacktest: () => void;
  onAnalyze: () => void;
  onAiFix?: () => void;
  onSubmitSimulation?: () => void;
  onShare?: () => void;
}

export function StrategyWorkspace({
  activeTab,
  onTabChange,
  runStatus,
  editorCode,
  onEditorChange,
  isGenerating,
  editorReadOnly,
  sessionState,
  jqcliConfigured,
  lastMetrics,
  isAnalyzing,
  logLines,
  performanceSeries,
  tradeGroups,
  holdingGroups,
  onRunBacktest,
  onAbortBacktest,
  onAnalyze,
  onAiFix,
  onSubmitSimulation,
  onShare,
}: StrategyWorkspaceProps) {
  return (
    <div className="flex min-h-0 min-w-[480px] flex-1 flex-col bg-white">
      <WorkspaceHeader
        activeTab={activeTab}
        onTabChange={onTabChange}
        sessionState={sessionState}
        jqcliConfigured={jqcliConfigured}
        lastMetrics={lastMetrics}
        isAnalyzing={isAnalyzing}
        runStatus={runStatus}
        onRunBacktest={onRunBacktest}
        onAbortBacktest={onAbortBacktest}
        onAnalyze={onAnalyze}
        onSubmitSimulation={onSubmitSimulation}
        onShare={onShare}
      />
      <div className="min-h-0 flex-1">
        {activeTab === "code" ? (
          <StrategyEditor
            className="h-full min-h-[360px]"
            code={editorCode}
            onChange={onEditorChange}
            isGenerating={isGenerating}
            readOnly={editorReadOnly}
          />
        ) : null}
        {activeTab === "performance" ? (
          <PerformancePanel metrics={lastMetrics} series={performanceSeries} />
        ) : null}
        {activeTab === "trades" ? (
          <TradeDetailsPanel groups={tradeGroups} />
        ) : null}
        {activeTab === "holdings" ? (
          <HoldingDetailsPanel groups={holdingGroups} />
        ) : null}
        {activeTab === "logs" ? (
          <RunLogPanel
            lines={logLines}
            isRunning={runStatus === "running"}
            onAiFix={onAiFix}
          />
        ) : null}
      </div>
    </div>
  );
}
