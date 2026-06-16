"use client";

import { ArrowUp, Link2, PanelLeft, Plus } from "lucide-react";

import { useWorkspaceShell } from "@/contexts/WorkspaceShellContext";

interface ChatColumnHeaderProps {
  title: string | null;
}

export function ChatColumnHeader({ title }: ChatColumnHeaderProps) {
  const { sidebarExpanded, openSidebar, handleNewChat } = useWorkspaceShell();

  return (
    <header className="flex h-11 shrink-0 items-center gap-0.5 px-4">
      {!sidebarExpanded ? (
        <>
          <button
            type="button"
            onClick={openSidebar}
            className="rounded-md p-1.5 text-gray-600 hover:bg-black/5"
            aria-label="展开侧栏"
          >
            <PanelLeft className="size-4" />
          </button>
          <button
            type="button"
            onClick={handleNewChat}
            className="rounded-md p-1.5 text-gray-600 hover:bg-black/5"
            aria-label="新对话"
          >
            <Plus className="size-4" />
          </button>
        </>
      ) : null}
      <h1 className="min-w-0 truncate text-sm font-medium text-gray-900">
        {title ?? "未命名对话"}
      </h1>
      <div className="ml-auto flex items-center gap-1">
        <button
          type="button"
          disabled
          aria-disabled="true"
          className="rounded-md p-1.5 text-gray-400 cursor-not-allowed opacity-50"
          aria-label="复制链接"
        >
          <Link2 className="size-4" />
        </button>
        <button
          type="button"
          disabled
          aria-disabled="true"
          className="rounded-md p-1.5 text-gray-400 cursor-not-allowed opacity-50"
          aria-label="返回顶部"
        >
          <ArrowUp className="size-4" />
        </button>
      </div>
    </header>
  );
}
