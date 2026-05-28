"use client";

import { useRouter } from "next/navigation";
import React from "react";

import { InputBox } from "@/components/workspace/InputBox";
import { MessageList } from "@/components/workspace/MessageList";
import { ThreadTitle } from "@/components/workspace/ThreadTitle";
import { useThread } from "@/hooks/useThreads";
import { useThreadStream } from "@/core/threads/hooks";

const NEW_THREAD_ID = "new";

export default function ChatPage({
  params,
}: {
  params: Promise<{ thread_id: string }>;
}) {
  const { thread_id } = React.use(params);
  const router = useRouter();
  const isNewThread = thread_id === NEW_THREAD_ID;
  const { data: thread } = useThread(isNewThread ? null : thread_id);

  const { messages, isLoading, sendMessage } = useThreadStream({
    threadId: isNewThread ? null : thread_id,
    onThreadId: (newThreadId) => {
      if (isNewThread) {
        router.replace(`/workspace/chats/${newThreadId}`);
      }
    },
  });

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="border-b px-4 py-3">
        <ThreadTitle
          threadId={thread_id}
          title={thread?.title ?? null}
        />
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-auto">
        <MessageList messages={messages} isLoading={isLoading} />
      </div>

      {/* Input */}
      <InputBox onSend={sendMessage} disabled={isLoading} />
    </div>
  );
}
