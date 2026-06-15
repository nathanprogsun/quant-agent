"use client";

import { ThreadTitle } from "@/components/workspace/ThreadTitle";

interface ChatWorkspaceHeaderProps {
  threadId: string;
  title: string | null;
}

export function ChatWorkspaceHeader({
  threadId,
  title,
}: ChatWorkspaceHeaderProps) {
  return (
    <header className="flex items-center border-b px-4 py-3">
      <ThreadTitle threadId={threadId} title={title} />
    </header>
  );
}
