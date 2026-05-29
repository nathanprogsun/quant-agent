'use client'

import type { BacktestMetrics } from '@/core/chat/types'

interface BacktestProgressProps {
  status: 'pending' | 'running' | 'done' | 'failed' | 'cancelled'
  message?: string
  metrics?: BacktestMetrics
  error?: string
}

export function BacktestProgress({ status, message, metrics, error }: BacktestProgressProps) {
  if (status === 'failed') {
    return (
      <div className="rounded-md border border-red-200 bg-red-50 p-4">
        <p className="text-red-800">回测失败: {error ?? '未知错误'}</p>
      </div>
    )
  }

  if (status === 'done' && metrics) {
    return (
      <div className="rounded-md border border-green-200 bg-green-50 p-4 space-y-1">
        <p className="font-medium text-green-800">回测完成</p>
        {metrics.annual_return != null && (
          <p>年化收益: {(metrics.annual_return * 100).toFixed(2)}%</p>
        )}
        {metrics.sharpe != null && <p>夏普比率: {metrics.sharpe.toFixed(2)}</p>}
        {metrics.max_drawdown != null && (
          <p>最大回撤: {(metrics.max_drawdown * 100).toFixed(2)}%</p>
        )}
      </div>
    )
  }

  return (
    <div className="rounded-md border border-blue-200 bg-blue-50 p-4">
      <p className="text-blue-800">{message ?? '回测进行中...'}</p>
    </div>
  )
}
