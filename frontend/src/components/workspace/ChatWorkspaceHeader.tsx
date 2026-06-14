'use client'

import { AnalyzeButton } from '@/components/workspace/AnalyzeButton'
import { BacktestButton } from '@/components/workspace/BacktestButton'
import { ThreadTitle } from '@/components/workspace/ThreadTitle'
import type { BacktestMetrics, SessionState } from '@/core/chat/types'

interface ChatWorkspaceHeaderProps {
  threadId: string
  title: string | null
  sessionState: SessionState
  jqcliConfigured: boolean
  lastMetrics: BacktestMetrics | null
  isAnalyzing: boolean
  onRunBacktest: () => void
  onAbortBacktest: () => void
  onAnalyze: () => void
}

export function ChatWorkspaceHeader({
  threadId,
  title,
  sessionState,
  jqcliConfigured,
  lastMetrics,
  isAnalyzing,
  onRunBacktest,
  onAbortBacktest,
  onAnalyze,
}: ChatWorkspaceHeaderProps) {
  return (
    <header className="flex items-center justify-between gap-4 border-b px-4 py-3">
      <ThreadTitle threadId={threadId} title={title} />
      <div className="flex items-center gap-2">
        <span className="rounded-md border px-2 py-1 text-xs text-muted-foreground">
          {sessionState}
        </span>
        <BacktestButton
          state={sessionState}
          jqcliConfigured={jqcliConfigured}
          onRun={onRunBacktest}
          onAbort={onAbortBacktest}
        />
        <AnalyzeButton
          state={sessionState}
          lastMetricsAvailable={lastMetrics != null}
          isAnalyzing={isAnalyzing}
          onAnalyze={onAnalyze}
        />
      </div>
    </header>
  )
}
