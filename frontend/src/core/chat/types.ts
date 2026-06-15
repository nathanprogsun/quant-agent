export type SessionState = 'idle' | 'generating' | 'code_ready' | 'backtesting' | 'analyzed'

export interface BacktestMetrics {
  annual_return?: number
  sharpe?: number
  max_drawdown?: number
  volatility?: number
  win_rate?: number
  total_return?: number
}

export interface BacktestEvent {
  type:
    | 'backtest_started'
    | 'backtest_progress'
    | 'backtest_completed'
    | 'backtest_failed'
    | 'backtest_aborted'
    | 'backtest_log_line'
  backtest_id?: string
  message?: string
  line?: string
  metrics?: BacktestMetrics
  error?: string
}

export interface BacktestResultDetail {
  performance: Array<{
    date: string
    strategy: number
    relative: number
    benchmark: number
    position_pct?: number | null
  }>
  trades: Array<{
    date: string
    trades: Array<{
      symbol: string
      name: string
      side: string
      quantity: number
      price: number
    }>
  }>
  holdings: Array<{
    date: string
    holdings: Array<{
      symbol: string
      name: string
      quantity: number
      avg_cost: number
      close: number
      market_value: number
    }>
    summary?: {
      total_assets: number
      cash: number
      total_market_value: number
    }
  }>
}

export interface AnalyzeEvent {
  type: 'analyze_delta' | 'analyze_done'
  content?: string
  improvement_suggestions?: string[]
}

/** SSE event names emitted by POST /threads/{id}/runs/stream (LangGraph Platform). */
export type ChatStreamEventName =
  | 'metadata'
  | 'values'
  | 'messages'
  | 'updates'
  | 'custom'
  | 'error'
  | 'end'

export interface ChatStreamMetadataEvent {
  run_id: string
  thread_id: string
}

export interface ChatStreamErrorEvent {
  message: string
}
