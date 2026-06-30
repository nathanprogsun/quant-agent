export interface DefaultBacktestParams {
  start_date: string
  end_date: string
  initial_capital: number
  frequency: string
  benchmark: string
}

const PRODUCTION_BACKTEST_PARAMS: DefaultBacktestParams = {
  start_date: '2020-01-01',
  end_date: '2024-12-31',
  initial_capital: 100000,
  frequency: 'day',
  benchmark: '000300.XSHG',
}

/** Shorter range for local dev to keep jqcli backtests fast. */
const DEV_BACKTEST_PARAMS: DefaultBacktestParams = {
  start_date: '2024-01-01',
  end_date: '2024-05-31',
  initial_capital: 100000,
  frequency: 'day',
  benchmark: '000300.XSHG',
}

export function getDefaultBacktestParams(): DefaultBacktestParams {
  return process.env.NODE_ENV === 'development'
    ? DEV_BACKTEST_PARAMS
    : PRODUCTION_BACKTEST_PARAMS
}
