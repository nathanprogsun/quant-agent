"use client";

import { useMemo, useState } from "react";

import {
  PerformanceChart,
  type PerformancePoint,
} from "@/components/workspace/PerformanceChart";
import type { BacktestMetrics } from "@/core/chat/types";

type RangeKey = "1m" | "3m" | "6m" | "1y" | "all";

const RANGE_LABELS: Record<RangeKey, string> = {
  "1m": "1月",
  "3m": "3月",
  "6m": "6月",
  "1y": "1年",
  all: "全部",
};

interface PerformancePanelProps {
  metrics: BacktestMetrics | null;
  series: PerformancePoint[];
}

function formatPct(value: number | undefined | null): string {
  if (value == null || Number.isNaN(value)) return "—";
  return `${(value * 100).toFixed(2)}%`;
}

function sliceSeries(series: PerformancePoint[], range: RangeKey): PerformancePoint[] {
  if (range === "all" || series.length === 0) return series;
  const take = range === "1m" ? 1 : range === "3m" ? 3 : range === "6m" ? 6 : 12;
  return series.slice(-take);
}

export function PerformancePanel({ metrics, series }: PerformancePanelProps) {
  const [range, setRange] = useState<RangeKey>("all");
  const visibleSeries = useMemo(() => sliceSeries(series, range), [series, range]);

  const totalReturn = metrics?.total_return ?? metrics?.annual_return;

  return (
    <div className="flex h-full min-h-[320px] flex-col gap-4 p-4">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
        <Kpi label="累计收益" value={formatPct(totalReturn)} highlight />
        <Kpi label="年化收益" value={formatPct(metrics?.annual_return)} />
        <Kpi label="最大回撤" value={formatPct(metrics?.max_drawdown)} />
        <Kpi label="Sharpe" value={metrics?.sharpe?.toFixed(2) ?? "—"} />
        <Kpi label="胜率" value={formatPct(metrics?.win_rate)} />
      </div>

      <div className="flex gap-2">
        {(Object.keys(RANGE_LABELS) as RangeKey[]).map((key) => (
          <button
            key={key}
            type="button"
            onClick={() => setRange(key)}
            className={
              range === key
                ? "rounded-md bg-gray-900 px-3 py-1 text-xs text-white"
                : "rounded-md border px-3 py-1 text-xs text-gray-600 hover:bg-gray-50"
            }
          >
            {RANGE_LABELS[key]}
          </button>
        ))}
      </div>

      <PerformanceChart series={visibleSeries} />
    </div>
  );
}

function Kpi({
  label,
  value,
  highlight,
}: {
  label: string;
  value: string;
  highlight?: boolean;
}) {
  return (
    <div className="rounded-lg border bg-white p-3">
      <div className="text-xs text-gray-500">{label}</div>
      <div
        className={
          highlight
            ? "mt-1 text-lg font-semibold text-red-600"
            : "mt-1 text-lg font-semibold text-gray-900"
        }
      >
        {value}
      </div>
    </div>
  );
}
