export type SessionState = 'idle' | 'generating' | 'code_ready' | 'backtesting' | 'analyzed'

export interface BacktestMetrics {
  annual_return?: number
  sharpe?: number
  max_drawdown?: number
  volatility?: number
  win_rate?: number
}

export interface BacktestEvent {
  type: 'backtest_started' | 'backtest_progress' | 'backtest_completed' | 'backtest_failed' | 'backtest_aborted'
  backtest_id?: string
  message?: string
  metrics?: BacktestMetrics
  error?: string
}

export interface AnalyzeEvent {
  type: 'analyze_delta' | 'analyze_done'
  content?: string
  improvement_suggestions?: string[]
}
