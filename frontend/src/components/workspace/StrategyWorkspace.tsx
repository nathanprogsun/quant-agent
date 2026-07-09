"use client";

import { RunLogPanel } from "@/components/workspace/RunLogPanel";
import { PerformancePanel } from "@/components/workspace/PerformancePanel";
import { WorkspaceHeader } from "@/components/workspace/WorkspaceHeader";
import { StrategyEditor } from "@/components/workspace/StrategyEditor";
import type { BacktestMetrics, SessionState } from "@/core/chat/types";
import type { PerformancePoint } from "@/components/workspace/PerformanceChart";
import type { StrategyTab, RunStatus } from "@/hooks/useStrategyWorkspace";

interface StrategyWorkspaceProps {
  title: string | null;
  onClose: (() => void) | undefined;
  activeTab: StrategyTab;
  onTabChange: (tab: StrategyTab) => void;
  runStatus: RunStatus;
  hasRunResults?: boolean;
  editorCode: string;
  onEditorChange: (code: string) => void;
  isGenerating: boolean;
  editorReadOnly: boolean;
  sessionState: SessionState;
  jqcliConfigured: boolean;
  lastMetrics: BacktestMetrics | null;
  logLines: string[];
  performanceSeries: PerformancePoint[];
  onRunBacktest: () => void;
  onAbortBacktest: () => void;
}

export function StrategyWorkspace({
  title,
  onClose,
  activeTab,
  onTabChange,
  runStatus,
  hasRunResults = false,
  editorCode,
  onEditorChange,
  isGenerating,
  editorReadOnly,
  sessionState,
  jqcliConfigured,
  lastMetrics,
  logLines,
  performanceSeries,
  onRunBacktest,
  onAbortBacktest,
}: StrategyWorkspaceProps) {
  return (
    <div className="flex min-h-0 min-w-0 flex-1 flex-col bg-white">
      <WorkspaceHeader
        title={title ?? null}
        onClose={onClose}
        activeTab={activeTab}
        onTabChange={onTabChange}
        hasRunResults={hasRunResults}
        sessionState={sessionState}
        jqcliConfigured={jqcliConfigured}
        hasEditorCode={Boolean(editorCode.trim())}
        lastMetrics={lastMetrics ?? null}
        runStatus={runStatus}
        onRunBacktest={onRunBacktest}
        onAbortBacktest={onAbortBacktest}
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
        {activeTab === "logs" ? (
          <RunLogPanel
            lines={logLines}
            isRunning={runStatus === "running"}
          />
        ) : null}
      </div>
    </div>
  );
}