"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { useCreateThread, useDeleteThread, useThreads } from "@/hooks/useThreads";

export function ThreadList() {
  const router = useRouter();
  const { data: threads, isLoading } = useThreads();
  const createThread = useCreateThread();
  const deleteThread = useDeleteThread();
  const [createError, setCreateError] = useState<string | null>(null);

  const handleNewChat = () => {
    setCreateError(null);
    createThread.mutate(undefined, {
      onSuccess: (thread) => {
        router.push(`/workspace/chats/${thread.id}`);
      },
      onError: () => {
        setCreateError("创建对话失败，请稍后重试");
      },
    });
  };

  if (isLoading) {
    return <div className="p-4 text-gray-500">加载中...</div>;
  }

  return (
    <div className="space-y-2">
      <button
        onClick={handleNewChat}
        disabled={createThread.isPending}
        className="w-full rounded border border-dashed p-2 text-sm hover:bg-gray-100 disabled:cursor-not-allowed disabled:opacity-60"
      >
        {createThread.isPending ? "创建中..." : "+ 新对话"}
      </button>

      {createError ? (
        <p className="px-2 text-xs text-red-600">{createError}</p>
      ) : null}

      {threads?.map((thread) => (
        <div
          key={thread.id}
          className="group flex items-center justify-between rounded p-2 hover:bg-gray-100"
        >
          <a
            href={`/workspace/chats/${thread.id}`}
            className="flex-1 truncate text-sm"
          >
            {thread.title ?? "未命名对话"}
          </a>
          <button
            onClick={() => deleteThread.mutate(thread.id)}
            className="ml-2 text-gray-400 opacity-0 group-hover:opacity-100 hover:text-red-500"
          >
            x
          </button>
        </div>
      ))}

      {threads?.length === 0 && (
        <p className="p-2 text-sm text-gray-400">暂无对话</p>
      )}
    </div>
  );
}
