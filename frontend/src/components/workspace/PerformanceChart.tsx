"use client";

import {
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

export interface PerformancePoint {
  date: string;
  strategy: number;
  relative: number;
  benchmark: number;
}

interface PerformanceChartProps {
  series: PerformancePoint[];
}

export function PerformanceChart({ series }: PerformanceChartProps) {
  if (series.length === 0) {
    return (
      <div className="flex h-64 items-center justify-center text-sm text-gray-400">
        暂无曲线数据
      </div>
    );
  }

  return (
    <div className="h-72 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={series} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
          <XAxis dataKey="date" tick={{ fontSize: 11 }} />
          <YAxis yAxisId="left" tick={{ fontSize: 11 }} />
          <Tooltip />
          <Legend />
          <Line
            yAxisId="left"
            type="monotone"
            dataKey="strategy"
            name="策略收益"
            stroke="#ef4444"
            dot={false}
            strokeWidth={2}
          />
          <Line
            yAxisId="left"
            type="monotone"
            dataKey="relative"
            name="相对收益"
            stroke="#3b82f6"
            dot={false}
          />
          <Line
            yAxisId="left"
            type="monotone"
            dataKey="benchmark"
            name="基准"
            stroke="#9ca3af"
            dot={false}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}