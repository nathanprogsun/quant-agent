'use client'

import type { SessionState } from '@/core/chat/types'
import { Button } from '@/components/ui/button'

interface AnalyzeButtonProps {
  state: SessionState
  lastMetricsAvailable: boolean
  isAnalyzing: boolean
  onAnalyze: () => void
}

export function AnalyzeButton({
  state,
  lastMetricsAvailable,
  isAnalyzing,
  onAnalyze,
}: AnalyzeButtonProps) {
  const disabled =
    !lastMetricsAvailable ||
    isAnalyzing ||
    state === 'idle' ||
    state === 'generating' ||
    state === 'backtesting'

  return (
    <Button variant="outline" disabled={disabled} onClick={onAnalyze}>
      {isAnalyzing ? '分析中...' : '对比分析'}
    </Button>
  )
}
