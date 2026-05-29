'use client'

import { useState } from 'react'
import { Button } from '@/components/ui/button'

export default function IntegrationSettingsPage() {
  const [token, setToken] = useState('')
  const [status, setStatus] = useState<'idle' | 'testing' | 'ok' | 'error'>('idle')

  const testConnection = async () => {
    setStatus('testing')
    try {
      const res = await fetch('/api/v1/backtest/auth-check', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token }),
      })
      setStatus(res.ok ? 'ok' : 'error')
    } catch {
      setStatus('error')
    }
  }

  return (
    <div className="max-w-2xl mx-auto p-6 space-y-6">
      <h1 className="text-2xl font-bold">集成设置</h1>

      <div className="space-y-4">
        <div>
          <label className="block text-sm font-medium mb-1">jqcli Token</label>
          <input
            type="password"
            value={token}
            onChange={(e) => setToken(e.target.value)}
            className="w-full rounded-md border p-2"
            placeholder="输入 jqcli 认证 token"
          />
        </div>

        <Button onClick={testConnection} disabled={!token || status === 'testing'}>
          {status === 'testing' ? '测试中...' : '测试连接'}
        </Button>

        {status === 'ok' && <p className="text-green-600">连接成功</p>}
        {status === 'error' && <p className="text-red-600">连接失败，请检查 token</p>}
      </div>
    </div>
  )
}
