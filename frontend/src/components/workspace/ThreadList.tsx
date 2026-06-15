"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { useLoginModal } from "@/contexts/LoginModalContext";
import { useAuth } from "@/core/auth/AuthProvider";
import type { Thread } from "@/core/threads/types";
import { useCreateThread, useDeleteThread, useThreads } from "@/hooks/useThreads";

interface ThreadListProps {
  guest?: boolean;
}

type ThreadGroupKey = "today" | "within30" | "earlier";

const GROUP_LABELS: Record<ThreadGroupKey, string> = {
  today: "今天",
  within30: "30 天内",
  earlier: "更早",
};

function groupThreads(threads: Thread[]): Record<ThreadGroupKey, Thread[]> {
  const now = new Date();
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const thirtyDaysAgo = new Date(startOfToday);
  thirtyDaysAgo.setDate(thirtyDaysAgo.getDate() - 30);

  const groups: Record<ThreadGroupKey, Thread[]> = {
    today: [],
    within30: [],
    earlier: [],
  };

  for (const thread of threads) {
    const updated = new Date(thread.updated_at);
    if (updated >= startOfToday) {
      groups.today.push(thread);
    } else if (updated >= thirtyDaysAgo) {
      groups.within30.push(thread);
    } else {
      groups.earlier.push(thread);
    }
  }

  return groups;
}

export function ThreadList({ guest = false }: ThreadListProps) {
  const router = useRouter();
  const { isAuthenticated } = useAuth();
  const { openLoginModal } = useLoginModal();
  const { data: threads, isLoading } = useThreads({
    enabled: !guest && isAuthenticated,
  });
  const createThread = useCreateThread();
  const deleteThread = useDeleteThread();
  const [createError, setCreateError] = useState<string | null>(null);

  const handleNewChat = () => {
    if (guest || !isAuthenticated) {
      openLoginModal();
      return;
    }

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

  if (!guest && isLoading) {
    return <div className="p-4 text-gray-500">加载中...</div>;
  }

  const threadList = guest ? [] : threads ?? [];
  const grouped = groupThreads(threadList);

  return (
    <div className="space-y-3">
      <button
        onClick={handleNewChat}
        disabled={!guest && createThread.isPending}
        className="w-full rounded border border-dashed p-2 text-sm hover:bg-gray-100 disabled:cursor-not-allowed disabled:opacity-60"
      >
        {!guest && createThread.isPending ? "创建中..." : "+ 新对话"}
      </button>

      {createError ? (
        <p className="px-2 text-xs text-red-600">{createError}</p>
      ) : null}

      {(Object.keys(GROUP_LABELS) as ThreadGroupKey[]).map((key) => {
        const items = grouped[key];
        if (items.length === 0) return null;
        return (
          <div key={key}>
            <p className="px-2 pb-1 text-xs font-medium text-gray-400">
              {GROUP_LABELS[key]}
            </p>
            <div className="space-y-1">
              {items.map((thread) => (
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
            </div>
          </div>
        );
      })}

      {threadList.length === 0 && (
        <p className="p-2 text-sm text-gray-400">暂无对话</p>
      )}
    </div>
  );
}
