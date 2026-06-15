"use client";

import { useState } from "react";

interface ShareModalProps {
  open: boolean;
  onClose: () => void;
  shareUrl: string | null;
  isCreating?: boolean;
}

export function ShareModal({
  open,
  onClose,
  shareUrl,
  isCreating,
}: ShareModalProps) {
  const [copied, setCopied] = useState(false);

  if (!open) return null;

  const fullUrl =
    shareUrl && typeof window !== "undefined"
      ? `${window.location.origin}${shareUrl}`
      : "";

  const handleCopy = async () => {
    if (!fullUrl) return;
    await navigator.clipboard.writeText(fullUrl);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="w-full max-w-md rounded-lg border bg-white p-6 shadow-xl">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">分享对话</h2>
          <button type="button" onClick={onClose} className="text-gray-400 hover:text-gray-600">
            ×
          </button>
        </div>
        <p className="mt-2 text-sm text-gray-500">
          复制链接分享给已登录用户查看会话快照。
        </p>
        {isCreating ? (
          <p className="mt-4 text-sm text-gray-500">生成中…</p>
        ) : fullUrl ? (
          <div className="mt-4 space-y-3">
            <input
              readOnly
              value={fullUrl}
              className="w-full rounded border px-3 py-2 text-sm"
            />
            <button
              type="button"
              onClick={() => void handleCopy()}
              className="rounded bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-700"
            >
              {copied ? "已复制" : "复制链接"}
            </button>
          </div>
        ) : (
          <p className="mt-4 text-sm text-red-600">分享创建失败</p>
        )}
      </div>
    </div>
  );
}
