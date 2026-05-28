import { useState, useCallback } from 'react'
import type { SessionState } from './types'

interface SessionStateActions {
  generate: () => void
  codeComplete: () => void
  startBacktest: () => void
  backtestComplete: () => void
  backtestFailed: () => void
  analysisComplete: () => void
  reset: () => void
}

const VALID_TRANSITIONS: Record<SessionState, SessionState[]> = {
  idle: ['generating'],
  generating: ['code_ready', 'idle'],
  code_ready: ['backtesting', 'idle'],
  backtesting: ['analyzed', 'code_ready', 'idle'],
  analyzed: ['idle', 'generating'],
}

export function useSessionState(): { state: SessionState } & SessionStateActions {
  const [state, setState] = useState<SessionState>('idle')

  const transition = useCallback((target: SessionState) => {
    setState((current) => {
      if (VALID_TRANSITIONS[current]?.includes(target)) {
        return target
      }
      return current
    })
  }, [])

  return {
    state,
    generate: useCallback(() => transition('generating'), [transition]),
    codeComplete: useCallback(() => transition('code_ready'), [transition]),
    startBacktest: useCallback(() => transition('backtesting'), [transition]),
    backtestComplete: useCallback(() => transition('code_ready'), [transition]),
    backtestFailed: useCallback(() => transition('code_ready'), [transition]),
    analysisComplete: useCallback(() => transition('analyzed'), [transition]),
    reset: useCallback(() => transition('idle'), [transition]),
  }
}
