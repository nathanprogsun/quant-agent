"use client";

import { ArrowRight } from "lucide-react";

import { cn } from "@/lib/utils";

interface StrategyCodeCardProps {
  strategyName?: string;
  onOpenCode?: () => void;
}

function CodeIcon() {
  return (
    <svg
      width="22"
      height="22"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <polyline points="16 18 22 12 16 6" />
      <polyline points="8 6 2 12 8 18" />
    </svg>
  );
}

export function StrategyCodeCard({
  strategyName = "策略代码",
  onOpenCode,
}: StrategyCodeCardProps) {
  const ariaLabel = `打开${strategyName}`;

  return (
    <button
      type="button"
      onClick={onOpenCode}
      aria-label={ariaLabel}
      className={cn(
        "group/strategy-card relative mt-3 flex w-full max-w-sm items-center gap-3 overflow-hidden rounded-xl border border-gray-200 bg-white px-4 py-3 text-left",
        "shadow-sm transition-all duration-150",
        "hover:border-red-200 hover:bg-red-50/30 hover:shadow-md hover:-translate-y-px",
        "active:translate-y-0 active:shadow-sm",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-300 focus-visible:ring-offset-1",
      )}
    >
      <span
        aria-hidden
        className="absolute inset-y-0 left-0 w-1 bg-red-500 transition-all duration-150 group-hover/strategy-card:w-1.5"
      />
      <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-red-50 text-red-500 transition-colors group-hover/strategy-card:bg-red-100">
        <CodeIcon />
      </span>
      <span className="min-w-0 flex-1">
        <span className="block truncate text-sm font-semibold text-gray-900">
          {strategyName}
        </span>
        <span className="mt-0.5 block text-xs text-red-500">点击查看</span>
      </span>
      <ArrowRight
        aria-hidden
        className="size-4 shrink-0 text-gray-300 transition-all duration-150 group-hover/strategy-card:translate-x-0.5 group-hover/strategy-card:text-red-500"
      />
    </button>
  );
}