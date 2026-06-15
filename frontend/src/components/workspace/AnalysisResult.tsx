'use client'

import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

interface AnalysisResultProps {
  content: string
  isStreaming: boolean
}

export function AnalysisResult({ content, isStreaming }: AnalysisResultProps) {
  if (!content && !isStreaming) {
    return (
      <div className="rounded-md border border-gray-200 bg-gray-50 p-4">
        <p className="text-gray-500">等待分析...</p>
      </div>
    )
  }

  return (
    <div className="rounded-md border border-gray-200 p-4">
      <div className="prose prose-sm max-w-none dark:prose-invert">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
      </div>
      {isStreaming ? (
        <span className="mt-2 inline-block h-2 w-2 animate-pulse rounded-full bg-blue-500" />
      ) : null}
    </div>
  )
}
