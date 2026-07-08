"use client";

import type { CoTStep } from "@/core/messages/utils";
import {
  Reasoning,
  ReasoningContent,
  ReasoningTrigger,
} from "./Reasoning";

// Mirror the labels already used by ThinkingChain so the segmented UI speaks
// the same vocabulary as the legacy single-panel path.
const TOOL_LABELS: Record<string, string> = {
  lint_code_tool: "校验策略代码",
  validate_strategy_parameters: "校验策略参数",
};

function formatToolLabel(name: string): string {
  return TOOL_LABELS[name] ?? name.replace(/_/g, " ");
}

/** Deer-flow-style segmented chain-of-thought render.

 * Each CoTStep becomes its own collapsible row, in source order. Reasoning
 * rows reuse the existing ``<Reasoning>`` panel (slide-in animation, content
 * streamdown-rendered); tool_call rows are tiny status chips. ``isStreaming``
 * only marks the currently-open row; row lifecycle is handled internally by
 * ``<Reasoning>`` (auto-closes 1 s after stream ends — see Reasoning.tsx:42).
 *
 * Slice 2 deliverable: structural re-shape. Slice 3 binds the per-segment
 * lifecycle to "this is the latest unfinished AIMessage in the stream".
 */
export function CoTStepsView({
  steps,
}: {
  steps: CoTStep[];
}) {
  if (steps.length === 0) return null;
  return (
    <div className="space-y-2" data-testid="cot-steps">
      {steps.map((step) => {
        if (step.kind === "reasoning") {
          return (
            <Reasoning
              key={`r-${step.id}`}
              isStreaming={step.isStreaming}
              defaultOpen={step.isStreaming}
              className="mb-0"
            >
              <ReasoningTrigger />
              <ReasoningContent>{step.text}</ReasoningContent>
            </Reasoning>
          );
        }

        return (
          <div
            key={`tc-${step.id}`}
            className="flex items-center gap-2 px-1 text-xs text-gray-500"
            data-testid="cot-tool-step"
          >
            <span
              className={
                step.status === "done" ? "text-emerald-600" : "text-gray-400"
              }
            >
              {step.status === "done" ? "✓" : "…"}
            </span>
            <span>{formatToolLabel(step.name)}</span>
          </div>
        );
      })}
    </div>
  );
}

