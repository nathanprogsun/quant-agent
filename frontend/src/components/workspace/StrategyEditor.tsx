'use client'

import dynamic from 'next/dynamic'

import { cn } from '@/lib/utils'

const MonacoEditor = dynamic(() => import('@monaco-editor/react'), {
  ssr: false,
  loading: () => (
    <div className="flex h-full items-center justify-center bg-[#1e1e1e] text-sm text-zinc-400">
      加载编辑器…
    </div>
  ),
})

export interface StrategyEditorProps {
  code: string
  onChange: (value: string) => void
  readOnly?: boolean
  isGenerating?: boolean
  className?: string
}

export function StrategyEditor({
  code,
  onChange,
  readOnly = false,
  isGenerating = false,
  className,
}: StrategyEditorProps) {
  const showPlaceholder = !code && !isGenerating

  return (
    <div className={cn('relative flex min-h-0 flex-col bg-[#1e1e1e]', className)}>
      {isGenerating && (
        <div className="absolute inset-x-0 top-0 z-10 border-b border-blue-500/40 bg-blue-950/80 px-3 py-1 text-xs text-blue-100">
          生成中…
        </div>
      )}
      {showPlaceholder ? (
        <div className="flex h-full flex-col justify-center px-6 text-sm text-zinc-400">
          <p className="font-mono text-zinc-300"># 策略代码将出现在这里</p>
          <p className="mt-2">与助手对话后，最新 Python 代码块会自动同步到此编辑器。</p>
        </div>
      ) : (
        <MonacoEditor
          height="100%"
          language="python"
          theme="vs-dark"
          value={code}
          onChange={(value) => onChange(value ?? '')}
          options={{
            readOnly: readOnly || isGenerating,
            minimap: { enabled: false },
            fontSize: 14,
            scrollBeyondLastLine: false,
            automaticLayout: true,
          }}
        />
      )}
    </div>
  )
}
