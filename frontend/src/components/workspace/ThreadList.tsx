"use client";

import { Inbox, MoreHorizontal } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { useAuth } from "@/core/auth/AuthProvider";
import type { Thread } from "@/core/threads/types";
import { useDeleteThread, useThreads } from "@/hooks/useThreads";
import { cn } from "@/lib/utils";

interface ThreadListProps {
  /** When false, show empty state (P-01 / guest), like JoinQuant home sidebar. */
  showHistory?: boolean;
}

type ThreadGroupKey = "today" | "within30" | "earlier";

const GROUP_LABELS: Record<ThreadGroupKey, string> = {
  today: "今天",
  within30: "30天内",
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

export function ThreadList({ showHistory = false }: ThreadListProps) {
  const pathname = usePathname();
  const activeThreadId = pathname.match(/\/workspace\/chats\/([^/]+)/)?.[1];
  const { isAuthenticated } = useAuth();
  const { data: threads, isLoading } = useThreads({
    enabled: showHistory && isAuthenticated,
  });
  const deleteThread = useDeleteThread();

  if (showHistory && isLoading) {
    return (
      <div className="flex flex-1 items-center justify-center p-4 text-sm text-gray-400">
        加载中...
      </div>
    );
  }

  const threadList = showHistory ? threads ?? [] : [];
  const grouped = groupThreads(threadList);
  const hasThreads = threadList.length > 0;

  if (!showHistory || !hasThreads) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center px-2 pb-8 text-gray-400">
        <Inbox className="size-12 stroke-[1.25] text-gray-300" aria-hidden />
        <p className="mt-3 text-sm text-gray-400">暂无对话</p>
      </div>
    );
  }

  return (
    <div className="space-y-1">
      {(Object.keys(GROUP_LABELS) as ThreadGroupKey[]).map((key) => {
        const items = grouped[key];
        if (items.length === 0) return null;
        return (
          <div key={key} className="mt-3">
            <p className="px-2 pb-1 text-xs font-medium text-gray-500">
              {GROUP_LABELS[key]}
            </p>
            <ul className="mt-0.5 space-y-0.5">
              {items.map((thread) => {
                const isActive = thread.id === activeThreadId;
                return (
                  <li key={thread.id} className="group flex items-center">
                    <Link
                      href={`/workspace/chats/${thread.id}`}
                      className={cn(
                        "flex-1 truncate rounded-lg px-2 py-2 text-sm text-gray-800 hover:bg-black/5",
                        isActive && "bg-gray-100",
                      )}
                    >
                      {thread.title ?? "未命名对话"}
                    </Link>
                    <button
                      type="button"
                      onClick={() => deleteThread.mutate(thread.id)}
                      className={cn(
                        "ml-1 rounded p-1 text-gray-400 hover:text-gray-600",
                        isActive ? "opacity-100" : "opacity-0 group-hover:opacity-100",
                      )}
                      aria-label="更多"
                    >
                      <MoreHorizontal className="size-4" />
                    </button>
                  </li>
                );
              })}
            </ul>
          </div>
        );
      })}
    </div>
  );
}
