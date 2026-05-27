"use client";

import { useCreateThread, useDeleteThread, useThreads } from "@/hooks/useThreads";

export function ThreadList() {
  const { data: threads, isLoading } = useThreads();
  const createThread = useCreateThread();
  const deleteThread = useDeleteThread();

  if (isLoading) {
    return <div className="p-4 text-gray-500">Loading...</div>;
  }

  return (
    <div className="space-y-2">
      <button
        onClick={() => createThread.mutate(undefined)}
        className="w-full rounded border border-dashed p-2 text-sm hover:bg-gray-100"
      >
        + New Chat
      </button>

      {threads?.map((thread) => (
        <div
          key={thread.id}
          className="group flex items-center justify-between rounded p-2 hover:bg-gray-100"
        >
          <a
            href={`/workspace/chats/${thread.id}`}
            className="flex-1 truncate text-sm"
          >
            {thread.title ?? "Untitled Chat"}
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
        <p className="p-2 text-sm text-gray-400">No chats yet</p>
      )}
    </div>
  );
}
