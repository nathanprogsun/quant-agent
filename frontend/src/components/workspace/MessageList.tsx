"use client";

import type { Message } from "@langchain/langgraph-sdk";
import { Fragment } from "react";
import { Streamdown } from "streamdown";

import { StrategyCodeCard } from "@/components/workspace/StrategyCodeCard";
import { ThinkingChain } from "@/components/workspace/ThinkingChain";
import {
  Reasoning,
  ReasoningContent,
  ReasoningTrigger,
} from "@/components/workspace/Reasoning";
import {
  extractContentFromMessage,
  extractReasoningFromMessage,
  extractThinkingToolStepsFromMessages,
  getLastAiMessage,
  getLastAssistantGroupMessages,
  getLastVisibleAiMessage,
  aiMessageHasToolCalls,
  splitThinkingFromText,
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

function MarkdownText({
  text,
  plainText,
}: {
  text: string;
  plainText?: boolean;
}) {
  const safeText = splitThinkingFromText(text).text;

  if (plainText) {
    return <p className="whitespace-pre-wrap text-sm">{safeText}</p>;
  }

  if (!safeText.trim()) return null;

  return (
    <Streamdown
      className="prose prose-sm max-w-none prose-headings:font-semibold prose-p:leading-relaxed prose-code:rounded prose-code:bg-gray-100 prose-code:px-1 prose-code:py-0.5 prose-code:before:content-none prose-code:after:content-none prose-pre:bg-gray-50"
      {...streamdownPlugins}
    >
      {safeText}
    </Streamdown>
  );
}

export function MessageList({
  messages,
  isLoading,
  threadTitle,
  onOpenCode,
}: MessageListProps) {
  const groups = getMessageGroups(messages);
  const lastAiMessage = getLastAiMessage(messages);
  const lastVisibleAiMessage = getLastVisibleAiMessage(messages);
  const lastAssistantMessages = getLastAssistantGroupMessages(messages);
  const streamingReasoning = lastAiMessage
    ? extractReasoningFromMessage(lastAiMessage)
    : "";
  const streamingResponseText = lastVisibleAiMessage
    ? extractContentFromMessage(lastVisibleAiMessage)
    : "";
  const visibleStreamingText = streamingResponseText
    ? splitThinkingFromText(streamingResponseText).text
    : "";
  const toolSteps = extractThinkingToolStepsFromMessages(lastAssistantMessages);
  const showThinkingOnly = Boolean(isLoading && !visibleStreamingText.trim());
  const showCollapsedThinking = Boolean(
    isLoading &&
      visibleStreamingText.trim() &&
      (streamingReasoning || toolSteps.length > 0),
  );

  if (groups.length === 0) {
    return (
      <div className="flex h-full flex-col py-4">
        {isLoading ? (
          <ThinkingChain isStreaming reasoning={streamingReasoning} toolSteps={toolSteps} />
        ) : (
          <div className="flex flex-1 items-center justify-center text-gray-400">
            开始对话吧
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="w-full space-y-6 py-4">
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
          const isStreamingGroup = Boolean(isLoading && index === groups.length - 1);
          return (
            <AssistantGroup
              key={groupKey}
              groupKey={groupKey}
              messages={group.messages}
              threadTitle={threadTitle}
              onOpenCode={onOpenCode}
              streamPlainText={isStreamingGroup}
              streamingReasoning={isStreamingGroup ? streamingReasoning : ""}
              toolSteps={isStreamingGroup ? toolSteps : []}
              showCollapsedThinking={isStreamingGroup && showCollapsedThinking}
            />
          );
        }

        return null;
      })}

      {showThinkingOnly ? (
        <ThinkingChain
          isStreaming
          reasoning={streamingReasoning}
          toolSteps={toolSteps}
          defaultOpen
        />
      ) : null}
    </div>
  );
}

function HumanMessage({ message }: { message: Message }) {
  const content = extractContentFromMessage(message);
  if (!content) return null;

  return (
    <div className="flex justify-end">
      <div className="max-w-[85%] rounded-2xl bg-gray-100 px-4 py-2 text-sm text-gray-900">
        <p className="whitespace-pre-wrap leading-relaxed">{content}</p>
      </div>
    </div>
  );
}

function AssistantGroup({
  groupKey,
  messages,
  threadTitle,
  onOpenCode,
  streamPlainText = false,
  streamingReasoning = "",
  toolSteps = [],
  showCollapsedThinking = false,
}: {
  groupKey: string;
  messages: Message[];
  threadTitle?: string | null;
  onOpenCode?: () => void;
  streamPlainText?: boolean;
  streamingReasoning?: string;
  toolSteps?: ReturnType<typeof extractThinkingToolStepsFromMessages>;
  showCollapsedThinking?: boolean;
}) {
  const aiMessages = messages.filter((m) => m.type === "ai");

  return (
    <div className="flex items-start gap-2">
      <div
        className="flex size-6 shrink-0 items-center justify-center rounded-full bg-red-500 text-[10px] font-bold text-white"
        aria-hidden="true"
      >
        <span>Q</span>
      </div>
      <div className="min-w-0 flex-1 space-y-3">
        {showCollapsedThinking ? (
          <ThinkingChain
            isStreaming
            reasoning={streamingReasoning}
            toolSteps={toolSteps}
            defaultOpen={false}
          />
        ) : null}
        {aiMessages
          .filter((msg) => {
            if (aiMessageHasToolCalls(msg)) return false;
            const hasContent = extractContentFromMessage(msg).length > 0;
            const hasReasoning = extractReasoningFromMessage(msg).length > 0;
            return hasContent || hasReasoning;
          })
          .map((msg, messageIndex) => {
            const rawContent = extractContentFromMessage(msg);
            const blockReasoning = extractReasoningFromMessage(msg);
            const { thinking, text: visibleText } = splitThinkingFromText(rawContent);
            const reasoningText = [blockReasoning, thinking]
              .filter(Boolean)
              .join("\n\n");
            const content = visibleText;
            if (!content && !reasoningText && !streamPlainText) return null;

            const parts = splitMarkdownWithPythonBlocks(content);
            const messageKey = getMessageKey(
              msg,
              `${groupKey}-response-${messageIndex}`,
            );

            return (
              <div key={messageKey} className="max-w-full text-sm text-gray-900">
                {reasoningText && !streamPlainText ? (
                  <Reasoning isStreaming={false} defaultOpen={false}>
                    <ReasoningTrigger />
                    <ReasoningContent>{reasoningText}</ReasoningContent>
                  </Reasoning>
                ) : null}
                {parts.map((part, partIndex) => {
                  if (part.type === "text" && part.text.trim()) {
                    return (
                      <MarkdownText
                        key={`${messageKey}-text-${partIndex}`}
                        text={part.text}
                        plainText={streamPlainText}
                      />
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
            );
          })}
      </div>
    </div>
  );
}
