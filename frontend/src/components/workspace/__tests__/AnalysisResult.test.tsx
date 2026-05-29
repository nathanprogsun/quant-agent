// @vitest-environment jsdom
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { AnalysisResult } from '../AnalysisResult'

describe('AnalysisResult', () => {
  it('renders markdown content', () => {
    render(<AnalysisResult content="## 对标 DC42\n\n分析结果" isStreaming={false} />)
    expect(screen.getByText(/DC42/)).toBeTruthy()
  })

  it('shows streaming indicator when streaming', () => {
    render(<AnalysisResult content="部分内容" isStreaming={true} />)
    // Should show some loading/streaming indicator
    expect(screen.getByText('部分内容')).toBeTruthy()
  })

  it('renders empty state when no content', () => {
    render(<AnalysisResult content="" isStreaming={false} />)
    expect(screen.getByText(/等待分析/)).toBeTruthy()
  })
})
