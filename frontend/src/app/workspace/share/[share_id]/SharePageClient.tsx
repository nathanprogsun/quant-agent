"use client";

import { useEffect, useState } from "react";

interface SharePageProps {
  shareId: string;
}

export function SharePageClient({ shareId }: SharePageProps) {
  const [data, setData] = useState<{
    title?: string;
    code?: string;
    messages?: Array<{ role?: string; content?: string }>;
    metrics?: Record<string, unknown>;
  } | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void (async () => {
      try {
        const res = await fetch(`/api/v1/share/${shareId}`, { credentials: "include" });
        if (!res.ok) throw new Error("无法加载分享");
        setData(await res.json());
      } catch (err) {
        setError(err instanceof Error ? err.message : "加载失败");
      }
    })();
  }, [shareId]);

  if (error) {
    return <p className="p-6 text-red-600">{error}</p>;
  }

  if (!data) {
    return <p className="p-6 text-gray-500">加载中…</p>;
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6 p-6">
      <h1 className="text-2xl font-bold">{data.title ?? "分享会话"}</h1>
      {data.metrics ? (
        <pre className="rounded border bg-gray-50 p-3 text-xs">
          {JSON.stringify(data.metrics, null, 2)}
        </pre>
      ) : null}
      {data.code ? (
        <pre className="rounded border bg-[#1e1e1e] p-4 text-xs text-zinc-100 overflow-auto">
          {data.code}
        </pre>
      ) : null}
      <div className="space-y-3">
        {(data.messages ?? []).map((msg, index) => (
          <div key={index} className="rounded border p-3 text-sm">
            <div className="font-medium text-gray-500">{msg.role ?? "message"}</div>
            <p className="mt-1 whitespace-pre-wrap">{msg.content ?? ""}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
