'use client'

import { useCallback, useEffect, useState } from 'react'

type AuthStatus = {
  configured: boolean
  authenticated: boolean
  username?: string | null
  message?: string
}

export default function IntegrationSettingsPage() {
  const [status, setStatus] = useState<AuthStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const loadStatus = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch('/api/v1/backtest/auth-check')
      if (!res.ok) {
        setError('无法读取集成状态')
        setStatus(null)
        return
      }
      const data = (await res.json()) as AuthStatus
      setStatus(data)
    } catch {
      setError('无法读取集成状态')
      setStatus(null)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadStatus()
  }, [loadStatus])

  return (
    <div className="max-w-2xl mx-auto p-6 space-y-6">
      <h1 className="text-2xl font-bold">集成设置</h1>

      <div className="rounded-md border p-4 space-y-3">
        <p className="text-sm text-muted-foreground">
          聚宽（jqcli）凭证由服务器环境变量配置（JQCLI_TOKEN、JQCLI_COOKIE、JQCLI_API_BASE）。
          如需启用回测，请联系管理员配置环境变量后重启服务。
        </p>

        {loading && <p className="text-sm">正在检查连接状态...</p>}
        {error && <p className="text-sm text-red-600">{error}</p>}

        {!loading && status && (
          <dl className="space-y-2 text-sm">
            <div className="flex justify-between gap-4">
              <dt className="text-muted-foreground">环境配置</dt>
              <dd>{status.configured ? '已配置' : '未配置'}</dd>
            </div>
            <div className="flex justify-between gap-4">
              <dt className="text-muted-foreground">认证状态</dt>
              <dd>{status.authenticated ? '已认证' : '未认证'}</dd>
            </div>
            {status.username && (
              <div className="flex justify-between gap-4">
                <dt className="text-muted-foreground">账号</dt>
                <dd>{status.username}</dd>
              </div>
            )}
            {status.message && (
              <p className="text-muted-foreground pt-2 border-t">{status.message}</p>
            )}
          </dl>
        )}
      </div>
    </div>
  )
}
