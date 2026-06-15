import { useCallback, useRef } from 'react'
import type { AnalyzeEvent } from './types'

interface AnalyzeStreamOptions {
  onDelta?: (content: string) => void
  onDone?: () => void
  onError?: (error: string) => void
}

export function useAnalyzeStream() {
  const abortRef = useRef<AbortController | null>(null)

  const startAnalyze = useCallback(
    async (
      payload: {
        thread_id: string
        backtest_id: string
        code: string
        metrics: Record<string, unknown>
      },
      options: AnalyzeStreamOptions = {},
    ) => {
      abortRef.current?.abort()
      const controller = new AbortController()
      abortRef.current = controller

      const response = await fetch('/api/v1/analyze/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
        signal: controller.signal,
      })

      if (!response.ok || !response.body) {
        options.onError?.('分析请求失败')
        return
      }

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const blocks = buffer.split('\n\n')
        buffer = blocks.pop() ?? ''

        for (const block of blocks) {
          for (const line of block.split('\n')) {
            if (!line.startsWith('data:')) continue
            const raw = line.slice(5).trim()
            if (!raw) continue
            try {
              const event = JSON.parse(raw) as AnalyzeEvent
              if (event.type === 'analyze_delta' && event.content) {
                options.onDelta?.(event.content)
              } else if (event.type === 'analyze_done') {
                options.onDone?.()
              }
            } catch {
              // Ignore malformed SSE payloads
            }
          }
        }
      }
    },
    [],
  )

  const cancelAnalyze = useCallback(() => {
    abortRef.current?.abort()
    abortRef.current = null
  }, [])

  return { startAnalyze, cancelAnalyze }
}
