// @vitest-environment jsdom
import { describe, it, expect } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useSessionState } from '../useSessionState'

describe('useSessionState', () => {
  it('starts in idle state', () => {
    const { result } = renderHook(() => useSessionState())
    expect(result.current.state).toBe('idle')
  })

  it('transitions idle → generating on generate()', () => {
    const { result } = renderHook(() => useSessionState())
    act(() => result.current.generate())
    expect(result.current.state).toBe('generating')
  })

  it('transitions idle → code_ready on codeComplete() for restored threads', () => {
    const { result } = renderHook(() => useSessionState())
    act(() => result.current.codeComplete())
    expect(result.current.state).toBe('code_ready')
  })

  it('transitions generating → code_ready on codeComplete()', () => {
    const { result } = renderHook(() => useSessionState())
    act(() => result.current.generate())
    act(() => result.current.codeComplete())
    expect(result.current.state).toBe('code_ready')
  })

  it('transitions code_ready → backtesting on startBacktest()', () => {
    const { result } = renderHook(() => useSessionState())
    act(() => result.current.generate())
    act(() => result.current.codeComplete())
    act(() => result.current.startBacktest())
    expect(result.current.state).toBe('backtesting')
  })

  it('stores lastMetrics on backtestComplete()', () => {
    const { result } = renderHook(() => useSessionState())
    act(() => result.current.generate())
    act(() => result.current.codeComplete())
    act(() => result.current.startBacktest())
    act(() =>
      result.current.backtestComplete({
        annual_return: 0.2,
        sharpe: 1.5,
      }),
    )
    expect(result.current.state).toBe('code_ready')
    expect(result.current.lastMetrics).toEqual({
      annual_return: 0.2,
      sharpe: 1.5,
    })
  })

  it('transitions backtesting → analyzed on analysisComplete()', () => {
    const { result } = renderHook(() => useSessionState())
    act(() => result.current.generate())
    act(() => result.current.codeComplete())
    act(() => result.current.startBacktest())
    act(() => result.current.analysisComplete())
    expect(result.current.state).toBe('analyzed')
  })

  it('transitions backtesting → code_ready on backtestFailed()', () => {
    const { result } = renderHook(() => useSessionState())
    act(() => result.current.generate())
    act(() => result.current.codeComplete())
    act(() => result.current.startBacktest())
    act(() => result.current.backtestFailed())
    expect(result.current.state).toBe('code_ready')
  })

  it('resets to idle from any state', () => {
    const { result } = renderHook(() => useSessionState())
    act(() => result.current.generate())
    act(() => result.current.reset())
    expect(result.current.state).toBe('idle')
  })
})
