"use client";

import type { Message } from "@langchain/langgraph-sdk";
import { Fragment } from "react";
import { Streamdown } from "streamdown";

import { StrategyCodeCard } from "@/components/workspace/StrategyCodeCard";
import {
  extractContentFromMessage,
  extractToolCallsFromMessage,
  getMessageGroups,
} from "@/core/messages/utils";
import { streamdownPlugins } from "@/core/streamdown/plugins";

interface MessageListProps {
  messages: Message[];
  isLoading?: boolean;
  threadTitle?: string | null;
  onOpenCode?: () => void;
}

function getMessageGroupKey(
  group: { type: string; id?: string; messages: Message[] },
  index: number,
): string {
  if (group.id) return group.id;

  const messageIds = group.messages
    .map((message) => message.id)
    .filter((id): id is string => Boolean(id))
    .join("-");

  return messageIds || `${group.type}-${index}`;
}

function getMessageKey(message: Message, fallback: string): string {
  return message.id ?? fallback;
}

function strategyNameFromCode(code: string, title?: string | null): string {
  if (title?.trim()) return title.trim();
  const comment = code.match(/^#\s*(.+)/m)?.[1]?.trim();
  return comment || "未命名策略";
}

type ContentPart =
  | { type: "text"; text: string }
  | { type: "python"; code: string };

function splitMarkdownWithPythonBlocks(content: string): ContentPart[] {
  const parts: ContentPart[] = [];
  const regex = /```python\s*\n([\s\S]*?)```/gi;
  let lastIndex = 0;

  for (const match of content.matchAll(regex)) {
    const index = match.index ?? 0;
    if (index > lastIndex) {
      parts.push({ type: "text", text: content.slice(lastIndex, index) });
    }
    parts.push({ type: "python", code: (match[1] ?? "").trim() });
    lastIndex = index + match[0].length;
  }

  if (lastIndex < content.length) {
    parts.push({ type: "text", text: content.slice(lastIndex) });
  }

  if (parts.length === 0 && content.trim()) {
    parts.push({ type: "text", text: content });
  }

  return parts;
}

export function MessageList({
  messages,
  isLoading,
  threadTitle,
  onOpenCode,
}: MessageListProps) {
  const groups = getMessageGroups(messages);
  const hasAssistantContent = messages.some(
    (message) =>
      message.type === "ai" && extractContentFromMessage(message).length > 0,
  );
  const showThinkingIndicator = Boolean(isLoading && !hasAssistantContent);

  if (groups.length === 0) {
    return (
      <div className="flex h-full items-center justify-center text-gray-400">
        {showThinkingIndicator ? "思考中..." : "开始对话吧"}
      </div>
    );
  }

  return (
    <div className="space-y-6 p-4">
      {groups.map((group, index) => {
        const groupKey = getMessageGroupKey(group, index);

        if (group.type === "human") {
          return (
            <Fragment key={groupKey}>
              {group.messages.map((msg, messageIndex) => (
                <HumanMessage
                  key={getMessageKey(msg, `${groupKey}-human-${messageIndex}`)}
                  message={msg}
                />
              ))}
            </Fragment>
          );
        }

        if (group.type === "assistant") {
          return (
            <AssistantGroup
              key={groupKey}
              groupKey={groupKey}
              messages={group.messages}
              threadTitle={threadTitle}
              onOpenCode={onOpenCode}
            />
          );
        }

        if (group.type === "tool") {
          return (
            <Fragment key={groupKey}>
              {group.messages.map((msg, messageIndex) => (
                <ToolMessage
                  key={getMessageKey(msg, `${groupKey}-tool-${messageIndex}`)}
                  message={msg}
                />
              ))}
            </Fragment>
          );
        }

        return null;
      })}

      {showThinkingIndicator ? (
        <div className="flex justify-start">
          <div className="rounded-lg bg-gray-100 px-4 py-2">
            <span className="animate-pulse">思考中...</span>
          </div>
        </div>
      ) : null}
    </div>
  );
}

function HumanMessage({ message }: { message: Message }) {
  const content = extractContentFromMessage(message);
  if (!content) return null;

  return (
    <div className="flex justify-end">
      <div className="max-w-[80%] rounded-lg bg-blue-600 px-4 py-2 text-white">
        <p className="whitespace-pre-wrap">{content}</p>
      </div>
    </div>
  );
}

function AssistantGroup({
  groupKey,
  messages,
  threadTitle,
  onOpenCode,
}: {
  groupKey: string;
  messages: Message[];
  threadTitle?: string | null;
  onOpenCode?: () => void;
}) {
  const aiMessages = messages.filter((m) => m.type === "ai");
  const toolMessages = messages.filter((m) => m.type === "tool");

  return (
    <div className="space-y-2">
      {aiMessages.map((msg, messageIndex) => {
        const toolCalls = extractToolCallsFromMessage(msg);
        if (toolCalls.length === 0) return null;

        const messageKey = getMessageKey(msg, `${groupKey}-ai-${messageIndex}`);

        return (
          <div key={`tc-${messageKey}`} className="space-y-1">
            {toolCalls.map((tc, toolCallIndex) => (
              <div
                key={tc.id || `${messageKey}-tc-${toolCallIndex}`}
                className="flex items-center gap-2 rounded bg-gray-50 px-3 py-1.5 text-sm text-gray-600"
              >
                <span className="inline-block h-2 w-2 rounded-full bg-yellow-400" />
                <span className="font-mono">{tc.name}</span>
                <span className="text-gray-400">
                  {JSON.stringify(tc.args).slice(0, 80)}
                </span>
              </div>
            ))}
          </div>
        );
      })}

      {toolMessages.map((msg, messageIndex) => (
        <ToolMessage
          key={getMessageKey(msg, `${groupKey}-tool-result-${messageIndex}`)}
          message={msg}
        />
      ))}

      {aiMessages
        .filter((msg) => extractContentFromMessage(msg).length > 0)
        .map((msg, messageIndex) => {
          const content = extractContentFromMessage(msg);
          const parts = splitMarkdownWithPythonBlocks(content);
          const messageKey = getMessageKey(
            msg,
            `${groupKey}-response-${messageIndex}`,
          );

          return (
            <div key={messageKey} className="flex justify-start">
              <div className="max-w-[90%] rounded-lg bg-gray-100 px-4 py-2 text-gray-900">
                {parts.map((part, partIndex) => {
                  if (part.type === "text" && part.text.trim()) {
                    return (
                      <Streamdown
                        key={`${messageKey}-text-${partIndex}`}
                        className="prose prose-sm max-w-none"
                        {...streamdownPlugins}
                      >
                        {part.text}
                      </Streamdown>
                    );
                  }

                  if (part.type === "python" && part.code) {
                    return (
                      <StrategyCodeCard
                        key={`${messageKey}-code-${partIndex}`}
                        strategyName={strategyNameFromCode(part.code, threadTitle)}
                        onOpenCode={onOpenCode}
                      />
                    );
                  }

                  return null;
                })}
              </div>
            </div>
          );
        })}
    </div>
  );
}

function ToolMessage({ message }: { message: Message }) {
  const content = extractContentFromMessage(message);
  if (!content) return null;

  return (
    <div className="flex justify-start pl-8">
      <div className="max-w-[70%] rounded border-l-2 border-gray-300 bg-gray-50 px-3 py-2 text-sm text-gray-600">
        <p className="whitespace-pre-wrap font-mono text-xs">{content}</p>
      </div>
    </div>
  );
}
