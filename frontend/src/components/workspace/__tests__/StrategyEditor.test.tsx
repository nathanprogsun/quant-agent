// @vitest-environment jsdom
import { describe, expect, it } from 'vitest'

import {
  extractLatestPythonBlockFromText,
  shouldSyncEditorCode,
} from '@/core/messages/pythonBlocks'

describe('StrategyEditor sync helpers', () => {
  it('extracts the latest python fenced block', () => {
    const text = [
      'first',
      '```python',
      'a = 1',
      '```',
      'later',
      '```python',
      'b = 2',
      '```',
    ].join('\n')

    expect(extractLatestPythonBlockFromText(text)).toBe('b = 2')
  })

  it('does not sync when assistant block is unchanged', () => {
    expect(shouldSyncEditorCode('x = 1', 'x = 1')).toBe(false)
  })

  it('syncs when assistant block is new', () => {
    expect(shouldSyncEditorCode('x = 2', 'x = 1')).toBe(true)
  })

  it('does not sync when no assistant block exists', () => {
    expect(shouldSyncEditorCode(null, 'x = 1')).toBe(false)
  })
})
