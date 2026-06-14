'use client'

import { cn } from '@/lib/utils'

interface WorkspaceDockProps {
  className?: string
}

/** Bottom dock shell — BacktestProgress / AnalysisResult wired in P3. */
export function WorkspaceDock({ className }: WorkspaceDockProps) {
  return (
    <section
      aria-label="工作区 Dock"
      className={cn(
        'max-h-60 shrink-0 border-t bg-muted/30 px-4 py-3 text-sm text-muted-foreground',
        className,
      )}
    >
      回测进度与分析报告将显示在此处（P3 接线）
    </section>
  )
}
