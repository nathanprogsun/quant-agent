import { useCallback, useRef } from 'react'
import type { BacktestEvent, BacktestMetrics } from './types'

interface BacktestStreamOptions {
  onComplete?: (metrics: BacktestMetrics) => void
  onFailed?: (error: string) => void
  onProgress?: (message: string) => void
  onStarted?: (backtestId: string) => void
  onAborted?: () => void
}

export function useBacktestStream(url: string, options: BacktestStreamOptions = {}) {
  const sourceRef = useRef<EventSource | null>(null)

  const connect = useCallback(() => {
    const source = new EventSource(url)
    sourceRef.current = source

    source.onmessage = (event: MessageEvent) => {
      try {
        const data: BacktestEvent = JSON.parse(event.data)

        switch (data.type) {
          case 'backtest_started':
            options.onStarted?.(data.backtest_id ?? '')
            break
          case 'backtest_progress':
            options.onProgress?.(data.message ?? '')
            break
          case 'backtest_completed':
            if (data.metrics) options.onComplete?.(data.metrics)
            break
          case 'backtest_failed':
            options.onFailed?.(data.error ?? '未知错误')
            break
          case 'backtest_aborted':
            options.onAborted?.()
            break
        }
      } catch {
        // Ignore malformed events
      }
    }

    source.onerror = () => {
      source.close()
      sourceRef.current = null
    }
  }, [url, options])

  const disconnect = useCallback(() => {
    sourceRef.current?.close()
    sourceRef.current = null
  }, [])

  return { connect, disconnect }
}
