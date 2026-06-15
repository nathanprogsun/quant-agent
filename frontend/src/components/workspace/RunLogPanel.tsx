"use client";

interface RunLogPanelProps {
  lines: string[];
  isRunning?: boolean;
  onAiFix?: () => void;
}

export function RunLogPanel({ lines, isRunning, onAiFix }: RunLogPanelProps) {
  return (
    <div className="flex h-full min-h-[320px] flex-col bg-[#1e1e1e] text-zinc-100">
      {isRunning ? (
        <div className="border-b border-zinc-700 px-3 py-2 text-sm text-amber-300">
          策略正在运行…
        </div>
      ) : null}
      <pre className="flex-1 overflow-auto p-3 text-xs leading-relaxed font-mono">
        {lines.length > 0 ? lines.join("\n") : "暂无日志"}
      </pre>
      {onAiFix && lines.length > 0 ? (
        <div className="border-t border-zinc-700 p-3">
          <button
            type="button"
            onClick={onAiFix}
            className="rounded bg-blue-600 px-3 py-1.5 text-sm text-white hover:bg-blue-700"
          >
            尝试 AI 修复代码
          </button>
        </div>
      ) : null}
    </div>
  );
}
