"use client";

import { WorkspaceHeader } from "@/components/workspace/WorkspaceHeader";
import { StrategyEditor } from "@/components/workspace/StrategyEditor";
import type { BacktestMetrics, SessionState } from "@/core/chat/types";
import type { StrategyTab } from "@/hooks/useStrategyWorkspace";

interface StrategyWorkspaceProps {
  activeTab: StrategyTab;
  onTabChange: (tab: StrategyTab) => void;
  editorCode: string;
  onEditorChange: (code: string) => void;
  isGenerating: boolean;
  editorReadOnly: boolean;
  sessionState: SessionState;
  jqcliConfigured: boolean;
  lastMetrics: BacktestMetrics | null;
  isAnalyzing: boolean;
  onRunBacktest: () => void;
  onAbortBacktest: () => void;
  onAnalyze: () => void;
}

function TabPlaceholder({ title }: { title: string }) {
  return (
    <div className="flex h-full min-h-[320px] items-center justify-center text-sm text-gray-400">
      {title}（即将上线）
    </div>
  );
}

export function StrategyWorkspace({
  activeTab,
  onTabChange,
  editorCode,
  onEditorChange,
  isGenerating,
  editorReadOnly,
  sessionState,
  jqcliConfigured,
  lastMetrics,
  isAnalyzing,
  onRunBacktest,
  onAbortBacktest,
  onAnalyze,
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
        onRunBacktest={onRunBacktest}
        onAbortBacktest={onAbortBacktest}
        onAnalyze={onAnalyze}
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
          <TabPlaceholder title="收益概况" />
        ) : null}
        {activeTab === "trades" ? (
          <TabPlaceholder title="交易详情" />
        ) : null}
        {activeTab === "holdings" ? (
          <TabPlaceholder title="持仓详情" />
        ) : null}
        {activeTab === "logs" ? (
          <TabPlaceholder title="运行日志" />
        ) : null}
      </div>
    </div>
  );
}
