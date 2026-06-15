"use client";

export interface HoldingRecord {
  symbol: string;
  name: string;
  quantity: number;
  avg_cost: number;
  close: number;
  market_value: number;
}

export interface HoldingDayGroup {
  date: string;
  holdings: HoldingRecord[];
  summary?: {
    total_assets: number;
    cash: number;
    total_market_value: number;
  };
}

interface HoldingDetailsPanelProps {
  groups: HoldingDayGroup[];
}

export function HoldingDetailsPanel({ groups }: HoldingDetailsPanelProps) {
  if (groups.length === 0) {
    return (
      <div className="flex h-full min-h-[320px] items-center justify-center text-sm text-gray-400">
        暂无持仓数据
      </div>
    );
  }

  return (
    <div className="h-full min-h-[320px] overflow-auto p-4">
      <div className="space-y-6">
        {groups.map((group) => (
          <div key={group.date}>
            <h3 className="mb-2 text-sm font-medium text-gray-700">{group.date}</h3>
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-gray-500">
                  <th className="py-2">代码</th>
                  <th className="py-2">名称</th>
                  <th className="py-2">数量</th>
                  <th className="py-2">成本</th>
                  <th className="py-2">收盘</th>
                  <th className="py-2">市值</th>
                </tr>
              </thead>
              <tbody>
                {group.holdings.map((row, index) => (
                  <tr key={`${group.date}-${index}`} className="border-b">
                    <td className="py-2 font-mono">{row.symbol}</td>
                    <td className="py-2">{row.name}</td>
                    <td className="py-2">{row.quantity}</td>
                    <td className="py-2">{row.avg_cost}</td>
                    <td className="py-2">{row.close}</td>
                    <td className="py-2">{row.market_value}</td>
                  </tr>
                ))}
                {group.summary ? (
                  <tr className="bg-gray-50 font-medium">
                    <td className="py-2" colSpan={3}>汇总</td>
                    <td className="py-2">现金 {group.summary.cash}</td>
                    <td className="py-2">市值 {group.summary.total_market_value}</td>
                    <td className="py-2">总资产 {group.summary.total_assets}</td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        ))}
      </div>
    </div>
  );
}
