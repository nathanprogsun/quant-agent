// @vitest-environment jsdom
import { fireEvent, render, screen } from "@testing-library/react";
import { useRef } from "react";
import { afterEach, beforeAll, beforeEach, describe, expect, test, vi } from "vitest";

import { ResizableSplitter } from "@/components/workspace/ResizableSplitter";
import {
  SPLIT_RATIO_DEFAULT,
  SPLIT_RATIO_MAX,
  SPLIT_RATIO_MIN,
  SPLIT_RATIO_STORAGE_KEY,
  useStrategyWorkspace,
} from "@/hooks/useStrategyWorkspace";

// jsdom does not implement the Pointer Capture API; stub it so the
// component's pointer handlers run end-to-end in unit tests.
beforeAll(() => {
  if (typeof Element !== "undefined") {
    if (!Element.prototype.setPointerCapture) {
      Element.prototype.setPointerCapture = function () {};
    }
    if (!Element.prototype.releasePointerCapture) {
      Element.prototype.releasePointerCapture = function () {};
    }
    if (!Element.prototype.hasPointerCapture) {
      Element.prototype.hasPointerCapture = function () {
        return false;
      };
    }
  }
});

function Harness({
  onRatioChange,
  onReset,
  ratio,
  containerWidth = 1000,
  minRatio = SPLIT_RATIO_MIN,
  maxRatio = SPLIT_RATIO_MAX,
}: {
  onRatioChange: (r: number) => void;
  onReset: () => void;
  ratio: number;
  containerWidth?: number;
  minRatio?: number;
  maxRatio?: number;
}) {
  const ref = useRef<HTMLDivElement>(null);
  return (
    <div ref={ref} style={{ width: containerWidth, height: 200, position: "relative" }}>
      <ResizableSplitter
        containerRef={ref}
        ratio={ratio}
        onRatioChange={onRatioChange}
        onReset={onReset}
        minRatio={minRatio}
        maxRatio={maxRatio}
      />
    </div>
  );
}

function mockContainerRect(width: number) {
  Element.prototype.getBoundingClientRect = vi.fn(() => ({
    width,
    height: 200,
    top: 0,
    left: 0,
    right: width,
    bottom: 200,
    x: 0,
    y: 0,
    toJSON() {
      return this;
    },
  }));
}

describe("ResizableSplitter", () => {
  beforeEach(() => {
    mockContainerRect(1000);
  });

  test("emits a clamped ratio when dragging horizontally", () => {
    const onRatioChange = vi.fn();
    const onReset = vi.fn();
    render(
      <Harness
        onRatioChange={onRatioChange}
        onReset={onReset}
        ratio={SPLIT_RATIO_DEFAULT}
      />,
    );

    const handle = screen.getByRole("separator");

    // Drag to 50% (clientX=500 with width=1000)
    fireEvent.pointerDown(handle, { button: 0, clientX: 500, pointerId: 1 });
    fireEvent.pointerMove(handle, { clientX: 500, pointerId: 1 });
    fireEvent.pointerUp(handle, { pointerId: 1 });

    expect(onRatioChange).toHaveBeenCalled();
    const lastCall = onRatioChange.mock.calls.at(-1)?.[0] as number;
    expect(lastCall).toBeCloseTo(0.5, 5);
  });

  test("clamps the ratio to the configured min/max", () => {
    const onRatioChange = vi.fn();
    render(
      <Harness
        onRatioChange={onRatioChange}
        onReset={vi.fn()}
        ratio={SPLIT_RATIO_DEFAULT}
      />,
    );

    const handle = screen.getByRole("separator");

    // Try to drag far left (should clamp to minRatio=0.2)
    fireEvent.pointerDown(handle, { button: 0, clientX: 0, pointerId: 2 });
    fireEvent.pointerMove(handle, { clientX: 0, pointerId: 2 });
    expect(onRatioChange).toHaveBeenLastCalledWith(SPLIT_RATIO_MIN);

    // Try to drag far right (should clamp to maxRatio=0.8)
    fireEvent.pointerMove(handle, { clientX: 9999, pointerId: 2 });
    expect(onRatioChange).toHaveBeenLastCalledWith(SPLIT_RATIO_MAX);

    fireEvent.pointerUp(handle, { pointerId: 2 });
  });

  test("double-click triggers onReset", () => {
    const onReset = vi.fn();
    render(
      <Harness
        onRatioChange={vi.fn()}
        onReset={onReset}
        ratio={0.4}
      />,
    );

    const handle = screen.getByRole("separator");
    fireEvent.doubleClick(handle);

    expect(onReset).toHaveBeenCalledTimes(1);
  });

  test("keyboard arrow keys adjust the ratio by the small step", () => {
    const onRatioChange = vi.fn();
    render(
      <Harness
        onRatioChange={onRatioChange}
        onReset={vi.fn()}
        ratio={0.5}
      />,
    );

    const handle = screen.getByRole("separator");
    fireEvent.keyDown(handle, { key: "ArrowRight" });
    expect(onRatioChange).toHaveBeenLastCalledWith(0.52);

    fireEvent.keyDown(handle, { key: "ArrowLeft" });
    expect(onRatioChange).toHaveBeenLastCalledWith(0.48);
  });

  test("shift+arrow uses the larger step", () => {
    const onRatioChange = vi.fn();
    render(
      <Harness
        onRatioChange={onRatioChange}
        onReset={vi.fn()}
        ratio={0.5}
      />,
    );

    const handle = screen.getByRole("separator");
    fireEvent.keyDown(handle, { key: "ArrowRight", shiftKey: true });
    expect(onRatioChange).toHaveBeenLastCalledWith(0.6);
  });

  test("Enter resets the split", () => {
    const onReset = vi.fn();
    const onRatioChange = vi.fn();
    render(
      <Harness
        onRatioChange={onRatioChange}
        onReset={onReset}
        ratio={0.3}
      />,
    );

    const handle = screen.getByRole("separator");
    fireEvent.keyDown(handle, { key: "Enter" });

    expect(onReset).toHaveBeenCalledTimes(1);
    expect(onRatioChange).not.toHaveBeenCalled();
  });

  test("exposes aria-valuenow/min/max reflecting the current ratio", () => {
    render(
      <Harness
        onRatioChange={vi.fn()}
        onReset={vi.fn()}
        ratio={0.5}
      />,
    );

    const handle = screen.getByRole("separator");
    expect(handle.getAttribute("aria-valuenow")).toBe("50");
    expect(handle.getAttribute("aria-valuemin")).toBe(
      String(Math.round(SPLIT_RATIO_MIN * 100)),
    );
    expect(handle.getAttribute("aria-valuemax")).toBe(
      String(Math.round(SPLIT_RATIO_MAX * 100)),
    );
  });
});

describe("useStrategyWorkspace.splitRatio", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  afterEach(() => {
    window.localStorage.clear();
  });

  function Probe() {
    const w = useStrategyWorkspace();
    return (
      <div>
        <span data-testid="ratio">{w.splitRatio}</span>
        <button data-testid="set-90" onClick={() => w.setSplitRatio(0.9)}>
          set
        </button>
        <button data-testid="set-05" onClick={() => w.setSplitRatio(0.05)}>
          set low
        </button>
        <button data-testid="set-nan" onClick={() => w.setSplitRatio(Number.NaN)}>
          set nan
        </button>
        <button data-testid="reset" onClick={() => w.resetSplitRatio()}>
          reset
        </button>
      </div>
    );
  }

  test("starts at the default ratio when nothing is persisted", () => {
    render(<Probe />);
    expect(screen.getByTestId("ratio").textContent).toBe(String(SPLIT_RATIO_DEFAULT));
  });

  test("clamps out-of-range values to the configured bounds", () => {
    render(<Probe />);

    fireEvent.click(screen.getByTestId("set-90"));
    // 0.9 exceeds SPLIT_RATIO_MAX (0.8), so it clamps
    expect(Number(screen.getByTestId("ratio").textContent)).toBeCloseTo(SPLIT_RATIO_MAX, 5);

    fireEvent.click(screen.getByTestId("set-05"));
    // 0.05 is below SPLIT_RATIO_MIN (0.2), so it clamps
    expect(Number(screen.getByTestId("ratio").textContent)).toBeCloseTo(SPLIT_RATIO_MIN, 5);

    fireEvent.click(screen.getByTestId("set-nan"));
    // NaN falls back to the default
    expect(Number(screen.getByTestId("ratio").textContent)).toBe(SPLIT_RATIO_DEFAULT);
  });

  test("resetSplitRatio restores the default", () => {
    render(<Probe />);

    fireEvent.click(screen.getByTestId("set-90"));
    expect(Number(screen.getByTestId("ratio").textContent)).toBe(SPLIT_RATIO_MAX);

    fireEvent.click(screen.getByTestId("reset"));
    expect(Number(screen.getByTestId("ratio").textContent)).toBe(SPLIT_RATIO_DEFAULT);
  });

  test("persists the ratio to localStorage so it survives remounts", () => {
    const { unmount } = render(<Probe />);
    fireEvent.click(screen.getByTestId("set-90"));
    // setSplitRatio(0.9) clamps to SPLIT_RATIO_MAX=0.8
    expect(window.localStorage.getItem(SPLIT_RATIO_STORAGE_KEY)).toBe(
      String(SPLIT_RATIO_MAX),
    );

    unmount();

    render(<Probe />);
    expect(Number(screen.getByTestId("ratio").textContent)).toBeCloseTo(
      SPLIT_RATIO_MAX,
      5,
    );
  });

  test("ignores invalid stored values", () => {
    window.localStorage.setItem(SPLIT_RATIO_STORAGE_KEY, "not-a-number");

    render(<Probe />);
    expect(screen.getByTestId("ratio").textContent).toBe(String(SPLIT_RATIO_DEFAULT));
  });
});
