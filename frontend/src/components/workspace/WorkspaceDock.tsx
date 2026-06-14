'use client'

import { AnalysisResult } from '@/components/workspace/AnalysisResult'
import { BacktestProgress } from '@/components/workspace/BacktestProgress'
import type { BacktestMetrics } from '@/core/chat/types'
import { cn } from '@/lib/utils'

export type DockBacktestView =
  | { kind: 'hidden' }
  | {
      kind: 'backtest'
      status: 'pending' | 'running' | 'done' | 'failed' | 'cancelled'
      message?: string
      metrics?: BacktestMetrics
      error?: string
    }

export type DockAnalyzeView =
  | { kind: 'hidden' }
  | {
      kind: 'analyze'
      content: string
      isStreaming: boolean
    }

interface WorkspaceDockProps {
  className?: string
  backtest?: DockBacktestView
  analyze?: DockAnalyzeView
}

export function WorkspaceDock({ className, backtest, analyze }: WorkspaceDockProps) {
  const showAnalyze = analyze?.kind === 'analyze'
  const showBacktest = !showAnalyze && backtest?.kind === 'backtest'

  if (!showAnalyze && !showBacktest) {
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
      {showAnalyze ? (
        <AnalysisResult content={analyze.content} isStreaming={analyze.isStreaming} />
      ) : null}
      {showBacktest ? (
        <BacktestProgress
          status={backtest.status}
          message={backtest.message}
          metrics={backtest.metrics}
          error={backtest.error}
        />
      ) : null}
    </section>
  )
}
