'use client'

import type { SessionState } from '@/core/chat/types'
import { Button } from '@/components/ui/button'

interface BacktestButtonProps {
  state: SessionState
  jqcliConfigured?: boolean
  onRun: () => void
  onAbort: () => void
  runLabel?: string
}

export function BacktestButton({
  state,
  jqcliConfigured = true,
  onRun,
  onAbort,
  runLabel = '运行策略',
}: BacktestButtonProps) {
  const isBacktesting = state === 'backtesting'
  const isDisabled =
    !jqcliConfigured ||
    state === 'idle' ||
    state === 'generating' ||
    state === 'backtesting' ||
    state === 'analyzed'

  const tooltip = !jqcliConfigured
    ? '未配置 jqcli 环境变量，请联系管理员'
    : undefined

  return (
    <Button
      onClick={isBacktesting ? onAbort : onRun}
      disabled={isDisabled}
      variant={isBacktesting ? 'destructive' : 'default'}
      className="bg-red-500 hover:bg-red-600 transition-colors"
      title={tooltip}
    >
      {isBacktesting ? '回测进行中' : runLabel}
    </Button>
  )
}
