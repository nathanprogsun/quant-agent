"use client";

import type { Message } from "@langchain/langgraph-sdk";
import { CoinsIcon } from "lucide-react";
import { useMemo } from "react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface TokenUsageProps {
  messages: Message[];
  className?: string;
}

interface TokenUsageData {
  inputTokens: number;
  outputTokens: number;
  totalTokens: number;
}

function estimateTokenUsage(messages: Message[]): TokenUsageData | null {
  // Simple estimation based on message count and average lengths
  if (messages.length === 0) return null;

  let totalChars = 0;
  for (const msg of messages) {
    const content = typeof msg.content === "string"
      ? msg.content
      : JSON.stringify(msg.content);
    totalChars += content.length;
  }

  // Rough estimation: ~4 chars per token for English
  const totalTokens = Math.ceil(totalChars / 4);
  const inputTokens = Math.ceil(totalTokens * 0.3);
  const outputTokens = totalTokens - inputTokens;

  return {
    inputTokens,
    outputTokens,
    totalTokens,
  };
}

function formatTokenCount(count: number): string {
  if (count >= 1000000) {
    return `${(count / 1000000).toFixed(1)}M`;
  }
  if (count >= 1000) {
    return `${(count / 1000).toFixed(1)}K`;
  }
  return count.toString();
}

export function TokenUsage({ messages, className }: TokenUsageProps) {
  const usage = useMemo(
    () => estimateTokenUsage(messages),
    [messages],
  );

  if (!usage) {
    return null;
  }

  return (
    <div
      className={cn(
        "text-muted-foreground bg-background/70 hover:bg-background/90 flex h-auto items-center gap-1.5 rounded-full border px-2 py-1 text-xs font-normal",
        className,
      )}
    >
      <CoinsIcon size={14} />
      <span className="font-mono">
        {formatTokenCount(usage.totalTokens)} tokens
      </span>
    </div>
  );
}

export type { TokenUsageData };
