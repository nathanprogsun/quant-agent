'use client'

import { BacktestButton } from '@/components/workspace/BacktestButton'
import { ThreadTitle } from '@/components/workspace/ThreadTitle'
import { Button } from '@/components/ui/button'
import type { SessionState } from '@/core/chat/types'

interface ChatWorkspaceHeaderProps {
  threadId: string
  title: string | null
  sessionState: SessionState
  jqcliConfigured: boolean
  onRunBacktest: () => void
  onAbortBacktest: () => void
}

export function ChatWorkspaceHeader({
  threadId,
  title,
  sessionState,
  jqcliConfigured,
  onRunBacktest,
  onAbortBacktest,
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
        <Button variant="outline" disabled title="P4 接线">
          对比分析
        </Button>
      </div>
    </header>
  )
}
