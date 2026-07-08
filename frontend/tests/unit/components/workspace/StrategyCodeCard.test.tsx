// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test, vi } from "vitest";

import { StrategyCodeCard } from "@/components/workspace/StrategyCodeCard";

describe("StrategyCodeCard", () => {
  test("renders the default '策略代码' label when no name is provided", () => {
    render(<StrategyCodeCard />);

    expect(screen.getByText("策略代码")).toBeInTheDocument();
    expect(screen.getByText("点击查看")).toBeInTheDocument();
  });

  test("renders a custom strategy name", () => {
    render(<StrategyCodeCard strategyName="小市值策略" />);

    expect(screen.getByText("小市值策略")).toBeInTheDocument();
    expect(screen.getByText("点击查看")).toBeInTheDocument();
  });

  test("calls onOpenCode when clicked", async () => {
    const onOpenCode = vi.fn();
    render(
      <StrategyCodeCard strategyName="测试策略" onOpenCode={onOpenCode} />,
    );

    await userEvent.click(screen.getByRole("button"));

    expect(onOpenCode).toHaveBeenCalledTimes(1);
  });

  test("exposes an aria-label combining the strategy name with the action verb", () => {
    render(<StrategyCodeCard strategyName="小市值策略" />);

    expect(
      screen.getByRole("button", { name: "打开小市值策略" }),
    ).toBeInTheDocument();
  });

  test("renders an arrow indicator (right-pointing icon)", () => {
    const { container } = render(<StrategyCodeCard />);

    // ArrowRight icon from lucide-react renders an <svg> with stroke
    const svgs = container.querySelectorAll("svg");
    expect(svgs.length).toBeGreaterThan(0);
  });
});