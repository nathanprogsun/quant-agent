"use client";

export interface TradeRecord {
  symbol: string;
  name: string;
  side: string;
  quantity: number;
  price: number;
}

export interface TradeDayGroup {
  date: string;
  trades: TradeRecord[];
}

interface TradeDetailsPanelProps {
  groups: TradeDayGroup[];
}

export function TradeDetailsPanel({ groups }: TradeDetailsPanelProps) {
  if (groups.length === 0) {
    return (
      <div className="flex h-full min-h-[320px] items-center justify-center text-sm text-gray-400">
        暂无交易记录
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
                  <th className="py-2">方向</th>
                  <th className="py-2">数量</th>
                  <th className="py-2">价格</th>
                </tr>
              </thead>
              <tbody>
                {group.trades.map((trade, index) => (
                  <tr key={`${group.date}-${index}`} className="border-b">
                    <td className="py-2 font-mono">{trade.symbol}</td>
                    <td className="py-2">{trade.name}</td>
                    <td
                      className={
                        trade.side.includes("买")
                          ? "py-2 text-red-600"
                          : "py-2 text-green-600"
                      }
                    >
                      {trade.side}
                    </td>
                    <td className="py-2">{trade.quantity}</td>
                    <td className="py-2">{trade.price}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ))}
      </div>
    </div>
  );
}
