"use client";

interface StrategyCodeCardProps {
  strategyName: string;
  onOpenCode?: () => void;
}

export function StrategyCodeCard({
  strategyName,
  onOpenCode,
}: StrategyCodeCardProps) {
  return (
    <button
      type="button"
      onClick={onOpenCode}
      className="mt-3 flex w-full max-w-sm items-center gap-3 rounded-lg border border-gray-200 bg-white px-4 py-3 text-left shadow-sm transition hover:border-blue-300 hover:shadow-md"
    >
      <span className="flex h-10 w-10 items-center justify-center rounded-md bg-blue-50 text-blue-600">
        <svg
          width="20"
          height="20"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          aria-hidden
        >
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
          <path d="M14 2v6h6M10 13l-2 2 2 2M14 17h4" />
        </svg>
      </span>
      <span className="min-w-0 flex-1">
        <span className="block text-sm font-medium text-gray-900 truncate">
          {strategyName}
        </span>
        <span className="block text-xs text-gray-500">点击查看策略代码</span>
      </span>
    </button>
  );
}
