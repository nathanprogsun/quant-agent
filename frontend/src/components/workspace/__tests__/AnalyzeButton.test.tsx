// @vitest-environment jsdom
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { AnalyzeButton } from '../AnalyzeButton'

describe('AnalyzeButton', () => {
  it('is disabled without lastMetrics', () => {
    render(
      <AnalyzeButton
        state="code_ready"
        lastMetricsAvailable={false}
        isAnalyzing={false}
        onAnalyze={vi.fn()}
      />,
    )
    expect(screen.getByRole('button', { name: '对比分析' })).toBeDisabled()
  })

  it('is enabled when lastMetrics available and code_ready', () => {
    render(
      <AnalyzeButton
        state="code_ready"
        lastMetricsAvailable={true}
        isAnalyzing={false}
        onAnalyze={vi.fn()}
      />,
    )
    expect(screen.getByRole('button', { name: '对比分析' })).toBeEnabled()
  })

  it('calls onAnalyze when clicked', async () => {
    const onAnalyze = vi.fn()
    render(
      <AnalyzeButton
        state="code_ready"
        lastMetricsAvailable={true}
        isAnalyzing={false}
        onAnalyze={onAnalyze}
      />,
    )
    await userEvent.click(screen.getByRole('button', { name: '对比分析' }))
    expect(onAnalyze).toHaveBeenCalledOnce()
  })
})
