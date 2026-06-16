"use client";

interface StrategyCodeCardProps {
  strategyName: string;
  onOpenCode?: () => void;
}

function StrategyCubeIcon() {
  return (
    <svg
      width="22"
      height="22"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      aria-hidden
    >
      <path d="M12 3l8 4.5v9L12 21l-8-4.5v-9L12 3z" />
      <path d="M12 12l8-4.5M12 12v9M12 12L4 7.5" />
    </svg>
  );
}

export function StrategyCodeCard({
  strategyName,
  onOpenCode,
}: StrategyCodeCardProps) {
  return (
    <button
      type="button"
      onClick={onOpenCode}
      className="mt-3 flex w-full max-w-xs items-center gap-3 rounded-xl border border-gray-200 bg-gray-50 px-4 py-3 text-left transition hover:border-gray-300 hover:shadow-sm"
    >
      <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-md border border-gray-100 bg-white text-red-500">
        <StrategyCubeIcon />
      </span>
      <span className="min-w-0 flex-1">
        <span className="block truncate text-sm font-medium text-gray-900">
          {strategyName}
        </span>
        <span className="mt-0.5 block text-xs text-red-500">点击查看</span>
      </span>
    </button>
  );
}
