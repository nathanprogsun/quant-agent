'use client'

import type { SessionState } from '@/core/chat/types'
import { Button } from '@/components/ui/button'

interface BacktestButtonProps {
  state: SessionState
  onRun: () => void
  onAbort: () => void
}

export function BacktestButton({ state, onRun, onAbort }: BacktestButtonProps) {
  const isBacktesting = state === 'backtesting'
  const isDisabled = state === 'idle' || state === 'generating' || state === 'analyzed'

  return (
    <Button
      onClick={isBacktesting ? onAbort : onRun}
      disabled={isDisabled}
      variant={isBacktesting ? 'destructive' : 'default'}
    >
      {isBacktesting ? '中止回测' : '运行回测'}
    </Button>
  )
}
