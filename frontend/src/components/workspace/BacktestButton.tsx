'use client'

import type { SessionState } from '@/core/chat/types'
import { Button } from '@/components/ui/button'

interface BacktestButtonProps {
  state: SessionState
  jqcliConfigured?: boolean
  hasEditorCode?: boolean
  onRun: () => void
  onAbort: () => void
  runLabel?: string
}

function getDisabledReason(
  state: SessionState,
  jqcliConfigured: boolean,
  hasEditorCode: boolean,
): string | undefined {
  if (!jqcliConfigured) {
    return '未配置聚宽凭证（JQCLI_USERNAME/JQCLI_PASSWORD），请联系管理员'
  }
  if (state === 'idle') {
    return hasEditorCode
      ? '策略代码已就绪，正在同步会话状态…'
      : '请等待策略代码生成完成'
  }
  if (state === 'generating') {
    return '策略生成中，请稍候'
  }
  if (state === 'backtesting') {
    return '回测进行中'
  }
  if (state === 'analyzed') {
    return '已完成对比分析，如需重新回测请继续对话'
  }
  return undefined
}

export function BacktestButton({
  state,
  jqcliConfigured = true,
  hasEditorCode = true,
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

  const tooltip = getDisabledReason(state, jqcliConfigured, hasEditorCode)

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
