'use client'

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
      <div className="prose prose-sm max-w-none">
        {content.split('\n').map((line, i) => (
          <p key={i}>{line}</p>
        ))}
      </div>
      {isStreaming && (
        <span className="inline-block mt-2 h-2 w-2 animate-pulse rounded-full bg-blue-500" />
      )}
    </div>
  )
}
