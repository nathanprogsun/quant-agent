"use client";

import { Edit2, Inbox, MoreHorizontal, Star, Trash2 } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { useAuth } from "@/core/auth/AuthProvider";
import type { Thread } from "@/core/threads/types";
import { useDeleteThread, useThreads, useUpdateThread } from "@/hooks/useThreads";
import { cn } from "@/lib/utils";

interface ThreadListProps {
  /** When false, show empty state (P-01 / guest), like JoinQuant home sidebar. */
  showHistory?: boolean;
}

type ThreadGroupKey = "today" | "yesterday" | "within30" | "earlier";

const GROUP_LABELS: Record<ThreadGroupKey, string> = {
  today: "今天",
  yesterday: "昨天",
  within30: "30天内",
  earlier: "更早",
};

function groupThreads(threads: Thread[]): Record<ThreadGroupKey, Thread[]> {
  const now = new Date();
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const startOfYesterday = new Date(startOfToday);
  startOfYesterday.setDate(startOfYesterday.getDate() - 1);
  const thirtyDaysAgoStart = new Date(startOfToday);
  thirtyDaysAgoStart.setDate(thirtyDaysAgoStart.getDate() - 30);

  const groups: Record<ThreadGroupKey, Thread[]> = {
    today: [],
    yesterday: [],
    within30: [],
    earlier: [],
  };

  for (const thread of threads) {
    const created = new Date(thread.created_at);
    if (created >= startOfToday) {
      groups.today.push(thread);
    } else if (created >= startOfYesterday) {
      groups.yesterday.push(thread);
    } else if (created >= thirtyDaysAgoStart) {
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
  const updateThread = useUpdateThread();
  const [openMenuId, setOpenMenuId] = useState<string | null>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setOpenMenuId(null);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

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
                const isMenuOpen = openMenuId === thread.id;
                return (
                  <li key={thread.id} className="group relative flex items-center">
                    <Link
                      href={`/workspace/chats/${thread.id}`}
                      className={cn(
                        "flex-1 truncate rounded-lg px-2 py-2 text-sm text-gray-800 hover:bg-black/5",
                        isActive && "bg-gray-100",
                      )}
                    >
                      {thread.title ?? "未命名对话"}
                    </Link>
                    <div
                      className="relative ml-1"
                      ref={isMenuOpen ? menuRef : null}
                    >
                      <button
                        type="button"
                        onClick={() =>
                          setOpenMenuId(isMenuOpen ? null : thread.id)
                        }
                        className={cn(
                          "rounded p-1 text-gray-400 hover:text-gray-600",
                          isActive || isMenuOpen
                            ? "opacity-100"
                            : "opacity-0 group-hover:opacity-100",
                        )}
                        aria-label="更多"
                        aria-haspopup="menu"
                        aria-expanded={isMenuOpen}
                      >
                        <MoreHorizontal className="size-4" />
                      </button>
                      {isMenuOpen ? (
                        <div
                          role="menu"
                          className="absolute right-0 top-full z-20 mt-1 w-32 rounded-lg border border-gray-200 bg-white py-1 shadow-lg"
                        >
                          <button
                            type="button"
                            role="menuitem"
                            onClick={() => {
                              window.alert("收藏功能即将推出");
                              setOpenMenuId(null);
                            }}
                            className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-sm text-gray-700 hover:bg-gray-50"
                          >
                            <Star className="size-3.5" />
                            收藏
                          </button>
                          <button
                            type="button"
                            role="menuitem"
                            onClick={() => {
                              const newTitle = window.prompt(
                                "重命名对话",
                                thread.title ?? "",
                              );
                              if (
                                newTitle !== null &&
                                newTitle.trim() &&
                                newTitle !== thread.title
                              ) {
                                updateThread.mutate({
                                  threadId: thread.id,
                                  params: { title: newTitle.trim() },
                                });
                              }
                              setOpenMenuId(null);
                            }}
                            className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-sm text-gray-700 hover:bg-gray-50"
                          >
                            <Edit2 className="size-3.5" />
                            重命名
                          </button>
                          <button
                            type="button"
                            role="menuitem"
                            onClick={() => {
                              deleteThread.mutate(thread.id);
                              setOpenMenuId(null);
                            }}
                            className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-sm text-red-600 hover:bg-red-50"
                          >
                            <Trash2 className="size-3.5" />
                            删除
                          </button>
                        </div>
                      ) : null}
                    </div>
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
