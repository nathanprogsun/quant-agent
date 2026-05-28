// @vitest-environment jsdom
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { BacktestProgress } from '../BacktestProgress'

describe('BacktestProgress', () => {
  it('renders progress message', () => {
    render(<BacktestProgress status="running" message="聚宽排队中" />)
    expect(screen.getByText('聚宽排队中')).toBeTruthy()
  })

  it('renders completed metrics', () => {
    render(
      <BacktestProgress
        status="done"
        metrics={{ annual_return: 0.15, sharpe: 1.2, max_drawdown: 0.08 }}
      />
    )
    expect(screen.getByText(/15/)).toBeTruthy()
  })

  it('renders error message', () => {
    render(<BacktestProgress status="failed" error="回测超时" />)
    expect(screen.getByText(/回测超时/)).toBeTruthy()
  })
})
