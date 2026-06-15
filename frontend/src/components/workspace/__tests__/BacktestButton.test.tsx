// @vitest-environment jsdom
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { BacktestButton } from '../BacktestButton'

describe('BacktestButton', () => {
  it('shows "运行策略" when idle', () => {
    render(<BacktestButton state="code_ready" onRun={vi.fn()} onAbort={vi.fn()} />)
    expect(screen.getByText('运行策略')).toBeTruthy()
  })

  it('shows disabled label when backtesting', () => {
    render(<BacktestButton state="backtesting" onRun={vi.fn()} onAbort={vi.fn()} />)
    expect(screen.getByText('回测进行中')).toBeTruthy()
  })

  it('is disabled when generating', () => {
    render(<BacktestButton state="generating" onRun={vi.fn()} onAbort={vi.fn()} />)
    const button = screen.getByRole('button')
    expect(button.hasAttribute('disabled')).toBe(true)
  })

  it('is disabled when backtesting', () => {
    render(<BacktestButton state="backtesting" onRun={vi.fn()} onAbort={vi.fn()} />)
    const button = screen.getByRole('button')
    expect(button.hasAttribute('disabled')).toBe(true)
  })

  it('is disabled when jqcli is not configured', () => {
    render(
      <BacktestButton
        state="code_ready"
        jqcliConfigured={false}
        onRun={vi.fn()}
        onAbort={vi.fn()}
      />,
    )
    const button = screen.getByRole('button')
    expect(button.hasAttribute('disabled')).toBe(true)
    expect(button.getAttribute('title')).toContain('jqcli')
  })

  it('calls onRun when clicked in code_ready state', () => {
    const onRun = vi.fn()
    render(<BacktestButton state="code_ready" onRun={onRun} onAbort={vi.fn()} />)
    fireEvent.click(screen.getByRole('button'))
    expect(onRun).toHaveBeenCalled()
  })

  it('calls onAbort when clicked in backtesting state only if enabled', () => {
    const onAbort = vi.fn()
    render(<BacktestButton state="backtesting" onRun={vi.fn()} onAbort={onAbort} />)
    fireEvent.click(screen.getByRole('button'))
    expect(onAbort).not.toHaveBeenCalled()
  })
})
