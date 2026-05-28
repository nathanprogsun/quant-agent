// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useBacktestStream } from '../useBacktestStream'

// Mock EventSource
class MockEventSource {
  static instances: MockEventSource[] = []
  onmessage: ((event: MessageEvent) => void) | null = null
  onerror: ((event: Event) => void) | null = null
  close = vi.fn()
  url: string

  constructor(url: string) {
    this.url = url
    MockEventSource.instances.push(this)
  }

  simulateMessage(data: string) {
    this.onmessage?.(new MessageEvent('message', { data }))
  }

  simulateError() {
    this.onerror?.(new Event('error'))
  }
}

describe('useBacktestStream', () => {
  beforeEach(() => {
    MockEventSource.instances = []
    vi.stubGlobal('EventSource', MockEventSource as any)
  })

  it('creates EventSource on connect', () => {
    const { result } = renderHook(() => useBacktestStream('/api/stream'))
    act(() => result.current.connect())
    expect(MockEventSource.instances).toHaveLength(1)
  })

  it('parses backtest_completed events', () => {
    const onComplete = vi.fn()
    const { result } = renderHook(() => useBacktestStream('/api/stream', { onComplete }))
    act(() => result.current.connect())

    const es = MockEventSource.instances[0]
    act(() => es.simulateMessage(JSON.stringify({
      type: 'backtest_completed',
      metrics: { annual_return: 0.15 },
    })))

    expect(onComplete).toHaveBeenCalledWith({ annual_return: 0.15 })
  })

  it('handles backtest_failed events', () => {
    const onFailed = vi.fn()
    const { result } = renderHook(() => useBacktestStream('/api/stream', { onFailed }))
    act(() => result.current.connect())

    const es = MockEventSource.instances[0]
    act(() => es.simulateMessage(JSON.stringify({
      type: 'backtest_failed',
      error: '超时',
    })))

    expect(onFailed).toHaveBeenCalledWith('超时')
  })

  it('closes EventSource on disconnect', () => {
    const { result } = renderHook(() => useBacktestStream('/api/stream'))
    act(() => result.current.connect())
    act(() => result.current.disconnect())
    expect(MockEventSource.instances[0].close).toHaveBeenCalled()
  })
})
