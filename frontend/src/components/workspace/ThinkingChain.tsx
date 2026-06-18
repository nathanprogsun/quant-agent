"use client";

import { Streamdown } from "streamdown";

import {
  Reasoning,
  ReasoningContent,
  ReasoningTrigger,
} from "@/components/workspace/Reasoning";
import type { ThinkingToolStep } from "@/core/messages/utils";
import { reasoningPlugins } from "@/core/streamdown/plugins";

function DottedSpinner({ className = "size-10" }: { className?: string }) {
  return (
    <div
      className={`animate-spin rounded-full border-2 border-dashed border-gray-300 border-t-gray-400 ${className}`}
      aria-hidden
    />
  );
}

function formatToolLabel(name: string): string {
  const labels: Record<string, string> = {
    lint_code_tool: "校验策略代码",
    validate_strategy_parameters: "校验策略参数",
  };
  return labels[name] ?? name.replace(/_/g, " ");
}

export function ThinkingChain({
  isStreaming = true,
  reasoning,
  toolSteps = [],
  defaultOpen = true,
}: {
  isStreaming?: boolean;
  reasoning?: string;
  toolSteps?: ThinkingToolStep[];
  defaultOpen?: boolean;
}) {
  const reasoningText = reasoning?.trim() ?? "";
  const hasReasoning = reasoningText.length > 0;
  const hasTools = toolSteps.length > 0;
  const hasChainContent = hasReasoning || hasTools;

  if (!isStreaming && !hasChainContent) return null;

  return (
    <div className="space-y-3" data-testid="thinking-chain">
      <div className="flex items-start gap-2.5">
        <div
          className="flex size-7 shrink-0 items-center justify-center rounded-full border border-gray-200 bg-white text-xs font-semibold text-gray-800"
          aria-hidden
        >
          Q
        </div>
        <div className="min-w-0 flex-1 pt-0.5">
          <p className="text-xs text-gray-400">@StrategyBot</p>
          {hasChainContent ? (
            <Reasoning
              isStreaming={isStreaming}
              defaultOpen={defaultOpen}
              className="mb-0 mt-1"
            >
              <ReasoningTrigger />
              <ReasoningContent>
                {hasTools ? (
                  <ul className="mb-3 space-y-1.5 text-xs text-gray-500">
                    {toolSteps.map((step) => (
                      <li key={step.id} className="flex items-center gap-2">
                        <span
                          className={
                            step.status === "done"
                              ? "text-emerald-600"
                              : "text-gray-400"
                          }
                        >
                          {step.status === "done" ? "✓" : "…"}
                        </span>
                        <span>{formatToolLabel(step.name)}</span>
                      </li>
                    ))}
                  </ul>
                ) : null}
                {hasReasoning ? (
                  <div data-testid="thinking-reasoning-content">
                    <Streamdown
                      className="prose prose-sm max-w-none text-gray-600 prose-p:leading-relaxed"
                      {...reasoningPlugins}
                    >
                      {reasoningText}
                    </Streamdown>
                  </div>
                ) : null}
              </ReasoningContent>
            </Reasoning>
          ) : (
            <p className="mt-1 text-sm text-gray-900">
              {isStreaming ? "思考.." : "思考完成"}
            </p>
          )}
        </div>
      </div>

      {isStreaming && !hasChainContent ? (
        <div className="flex justify-center py-12">
          <DottedSpinner />
        </div>
      ) : null}
    </div>
  );
}
