'use client'

import { useState } from 'react'
import { Button } from '@/components/ui/button'

interface BacktestDefaults {
  startDate: string
  endDate: string
  initialCapital: number
  frequency: string
  benchmark: string
}

export default function BacktestSettingsPage() {
  const [defaults, setDefaults] = useState<BacktestDefaults>({
    startDate: '2020-01-01',
    endDate: '2024-12-31',
    initialCapital: 100000,
    frequency: 'day',
    benchmark: '000300.XSHG',
  })

  const save = async () => {
    localStorage.setItem('backtest_defaults', JSON.stringify(defaults))
  }

  return (
    <div className="max-w-2xl mx-auto p-6 space-y-6">
      <h1 className="text-2xl font-bold">回测参数设置</h1>

      <div className="space-y-4">
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium mb-1">开始日期</label>
            <input
              type="date"
              value={defaults.startDate}
              onChange={(e) => setDefaults({ ...defaults, startDate: e.target.value })}
              className="w-full rounded-md border p-2"
            />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">结束日期</label>
            <input
              type="date"
              value={defaults.endDate}
              onChange={(e) => setDefaults({ ...defaults, endDate: e.target.value })}
              className="w-full rounded-md border p-2"
            />
          </div>
        </div>

        <div>
          <label className="block text-sm font-medium mb-1">初始资金</label>
          <input
            type="number"
            value={defaults.initialCapital}
            onChange={(e) => setDefaults({ ...defaults, initialCapital: Number(e.target.value) })}
            className="w-full rounded-md border p-2"
          />
        </div>

        <div>
          <label className="block text-sm font-medium mb-1">基准</label>
          <input
            type="text"
            value={defaults.benchmark}
            onChange={(e) => setDefaults({ ...defaults, benchmark: e.target.value })}
            className="w-full rounded-md border p-2"
            placeholder="000300.XSHG"
          />
        </div>

        <Button onClick={save}>保存</Button>
      </div>
    </div>
  )
}
