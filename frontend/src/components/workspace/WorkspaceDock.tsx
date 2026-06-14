'use client'

import { BacktestProgress } from '@/components/workspace/BacktestProgress'
import type { BacktestMetrics } from '@/core/chat/types'
import { cn } from '@/lib/utils'

export type DockBacktestView =
  | { kind: 'hidden' }
  | {
      kind: 'progress'
      status: 'pending' | 'running' | 'done' | 'failed' | 'cancelled'
      message?: string
      metrics?: BacktestMetrics
      error?: string
    }

interface WorkspaceDockProps {
  className?: string
  backtest?: DockBacktestView
}

export function WorkspaceDock({ className, backtest }: WorkspaceDockProps) {
  if (!backtest || backtest.kind === 'hidden') {
    return null
  }

  return (
    <section
      aria-label="工作区 Dock"
      className={cn(
        'max-h-60 shrink-0 overflow-auto border-t bg-muted/30 px-4 py-3',
        className,
      )}
    >
      <BacktestProgress
        status={backtest.status}
        message={backtest.message}
        metrics={backtest.metrics}
        error={backtest.error}
      />
    </section>
  )
}
