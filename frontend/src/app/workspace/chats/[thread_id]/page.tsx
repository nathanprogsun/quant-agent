"use client";

import type { Message } from "@langchain/langgraph-sdk";
import { useRouter } from "next/navigation";
import React, { useEffect, useMemo, useRef, useState } from "react";

import { ChatWorkspaceHeader } from "@/components/workspace/ChatWorkspaceHeader";
import { InputBox } from "@/components/workspace/InputBox";
import { MessageList } from "@/components/workspace/MessageList";
import { StrategyEditor } from "@/components/workspace/StrategyEditor";
import { WorkspaceDock } from "@/components/workspace/WorkspaceDock";
import {
  extractLatestPythonBlock,
  shouldSyncEditorCode,
} from "@/core/messages/pythonBlocks";
import { useSessionState } from "@/core/chat/useSessionState";
import { useThread } from "@/hooks/useThreads";
import { NEW_THREAD_ID, useThreadStream } from "@/core/threads/hooks";

export default function ChatPage({
  params,
}: {
  params: Promise<{ thread_id: string }>;
}) {
  const { thread_id } = React.use(params);
  const router = useRouter();
  const isNewThread = thread_id === NEW_THREAD_ID;
  const { data: thread } = useThread(isNewThread ? null : thread_id);

  const {
    state: sessionState,
    generate,
    codeComplete,
    reset,
  } = useSessionState();

  const [editorCode, setEditorCode] = useState("");
  const lastSyncedBlockRef = useRef<string | null>(null);
  const wasLoadingRef = useRef(false);

  const { messages, isLoading, sendMessage, pendingNavigationThreadId, values } =
    useThreadStream({
      threadId: isNewThread ? null : thread_id,
      onCreated: () => {
        // Defer URL update until the run finishes so history/checkpoint stay in sync.
      },
      onFinish: () => {
        const nextThreadId = pendingNavigationThreadId.current;
        if (isNewThread && nextThreadId) {
          router.replace(`/workspace/chats/${nextThreadId}`);
        }
      },
    });

  const latestPythonBlock = useMemo(
    () => extractLatestPythonBlock(messages as Message[]),
    [messages],
  );

  const showStrategyEditor = Boolean(
    editorCode.trim() ||
      latestPythonBlock ||
      sessionState === "code_ready" ||
      sessionState === "backtesting" ||
      sessionState === "analyzed",
  );

  useEffect(() => {
    if (isLoading && !wasLoadingRef.current) {
      generate();
    }

    if (!isLoading && wasLoadingRef.current) {
      if (latestPythonBlock) {
        codeComplete();
      } else {
        reset();
      }
    }

    wasLoadingRef.current = isLoading;
  }, [isLoading, latestPythonBlock, generate, codeComplete, reset]);

  useEffect(() => {
    if (
      shouldSyncEditorCode(latestPythonBlock, lastSyncedBlockRef.current) &&
      latestPythonBlock
    ) {
      setEditorCode(latestPythonBlock);
      lastSyncedBlockRef.current = latestPythonBlock;
    }
  }, [latestPythonBlock]);

  return (
    <div className="flex h-full min-h-0 flex-col">
      <ChatWorkspaceHeader
        threadId={thread_id}
        title={
          thread?.title ??
          (typeof values?.title === "string" ? values.title : null)
        }
        sessionState={sessionState}
      />

      <div
        className={
          showStrategyEditor
            ? "grid min-h-0 flex-1 grid-cols-[42fr_58fr] grid-rows-[minmax(0,1fr)_auto_auto]"
            : "grid min-h-0 flex-1 grid-rows-[minmax(0,1fr)_auto_auto]"
        }
      >
        <div
          className={
            showStrategyEditor
              ? "flex min-h-0 flex-col border-r"
              : "flex min-h-0 flex-col"
          }
        >
          <div className="min-h-0 flex-1 overflow-auto">
            <MessageList messages={messages} isLoading={isLoading} />
          </div>
        </div>

        {showStrategyEditor ? (
          <StrategyEditor
            className="min-h-[360px]"
            code={editorCode}
            onChange={setEditorCode}
            isGenerating={isLoading}
            readOnly={isLoading}
          />
        ) : null}

        <WorkspaceDock className={showStrategyEditor ? "col-span-2" : undefined} />

        <div className={showStrategyEditor ? "border-r" : undefined}>
          <InputBox onSend={sendMessage} disabled={isLoading} />
        </div>
        {showStrategyEditor ? (
          <div aria-hidden className="bg-[#1e1e1e]" />
        ) : null}
      </div>
    </div>
  );
}
