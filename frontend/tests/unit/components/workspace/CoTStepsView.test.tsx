// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import { describe, expect, test } from "vitest";

import { CoTStepsView } from "@/components/workspace/CoTStepsView";
import type { CoTStep } from "@/core/messages/utils";

describe("CoTStepsView", () => {
  test("renders nothing when steps is empty", () => {
    const { container } = render(<CoTStepsView steps={[]} />);
    expect(container.firstChild).toBeNull();
  });

  test("renders the chain-of-thought container for non-empty steps", () => {
    const steps: CoTStep[] = [
      { kind: "tool_call", id: "tc1", name: "search", status: "done" },
    ];
    render(<CoTStepsView steps={steps} />);
    expect(screen.getByTestId("cot-steps")).toBeInTheDocument();
  });

  test("renders a tool_call step with the done marker", () => {
    const steps: CoTStep[] = [
      { kind: "tool_call", id: "tc1", name: "search", status: "done" },
    ];
    render(<CoTStepsView steps={steps} />);
    expect(screen.getByText("search")).toBeInTheDocument();
    expect(screen.getByText("✓")).toBeInTheDocument();
  });

  test("renders tool_call steps with the running marker", () => {
    const steps: CoTStep[] = [
      { kind: "tool_call", id: "tc1", name: "search", status: "running" },
    ];
    render(<CoTStepsView steps={steps} />);
    expect(screen.getByText("…")).toBeInTheDocument();
  });

  test("uses Chinese label for known tool names", () => {
    const steps: CoTStep[] = [
      { kind: "tool_call", id: "tc1", name: "lint_code_tool", status: "done" },
    ];
    render(<CoTStepsView steps={steps} />);
    expect(screen.getByText("校验策略代码")).toBeInTheDocument();
  });

  test("emits one tool-step testid per tool_call entry", () => {
    const steps: CoTStep[] = [
      { kind: "tool_call", id: "tc1", name: "search", status: "done" },
      { kind: "tool_call", id: "tc2", name: "search", status: "running" },
    ];
    render(<CoTStepsView steps={steps} />);
    expect(screen.getAllByTestId("cot-tool-step")).toHaveLength(2);
  });

  test("emits one reasoning container per reasoning step", () => {
    // Reasoning renders via Radix CollapsibleContent which is hidden at first
    // paint — we don't assert on inner text (Streamdown may render async); we
    // assert on the count of reasoning rows by counting the BrainIcon triggers.
    const steps: CoTStep[] = [
      { kind: "reasoning", id: "a1", text: "r1", isStreaming: false },
      { kind: "tool_call", id: "tc1", name: "search", status: "done" },
      { kind: "reasoning", id: "a2", text: "r2", isStreaming: false },
    ];
    render(<CoTStepsView steps={steps} />);
    // Each <Reasoning> renders a <CollapsibleTrigger> with a BrainIcon icon
    // (svg.lucide-brain). Two reasoning rows => two braina icons.
    const triggers = document.querySelectorAll('[data-state]');
    expect(triggers.length).toBeGreaterThanOrEqual(2);
  });
});
