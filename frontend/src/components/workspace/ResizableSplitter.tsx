"use client";

import { useCallback, useEffect, useRef, type PointerEvent as ReactPointerEvent } from "react";

import { cn } from "@/lib/utils";

interface ResizableSplitterProps {
  /** Container element to measure; the splitter moves along its width. */
  containerRef: React.RefObject<HTMLElement | null>;
  /** Current ratio (0..1) of the LEFT pane relative to the container. */
  ratio: number;
  /** Called continuously while dragging. Receives the clamped ratio. */
  onRatioChange: (ratio: number) => void;
  /** Called on double-click; typically resets the ratio to its default. */
  onReset: () => void;
  /** Minimum allowed ratio (default 0.2). */
  minRatio?: number;
  /** Maximum allowed ratio (default 0.8). */
  maxRatio?: number;
  /** Visual orientation. Defaults to vertical (drags left/right). */
  orientation?: "vertical" | "horizontal";
  className?: string;
  ariaLabel?: string;
}

const DEFAULT_MIN = 0.2;
const DEFAULT_MAX = 0.8;

/**
 * Drag handle that resizes two adjacent panes. Mouse / touch / keyboard
 * accessible, and a double-click resets the split to its default.
 */
export function ResizableSplitter({
  containerRef,
  ratio,
  onRatioChange,
  onReset,
  minRatio = DEFAULT_MIN,
  maxRatio = DEFAULT_MAX,
  orientation = "vertical",
  className,
  ariaLabel = "拖动以调整左右面板宽度",
}: ResizableSplitterProps) {
  const draggingRef = useRef(false);
  const pointerIdRef = useRef<number | null>(null);

  const computeRatio = useCallback(
    (clientCoord: number) => {
      const container = containerRef.current;
      if (!container) return ratio;
      const rect = container.getBoundingClientRect();
      const size = orientation === "vertical" ? rect.width : rect.height;
      if (size <= 0) return ratio;
      const offset =
        orientation === "vertical" ? clientCoord - rect.left : clientCoord - rect.top;
      const next = offset / size;
      return Math.min(maxRatio, Math.max(minRatio, next));
    },
    [containerRef, minRatio, maxRatio, ratio, orientation],
  );

  const handlePointerDown = useCallback(
    (event: ReactPointerEvent<HTMLDivElement>) => {
      if (event.button !== 0 && event.pointerType === "mouse") return;
      const target = event.currentTarget;
      target.setPointerCapture(event.pointerId);
      pointerIdRef.current = event.pointerId;
      draggingRef.current = true;
      onRatioChange(computeRatio(event.clientX));
      event.preventDefault();
    },
    [computeRatio, onRatioChange],
  );

  const handlePointerMove = useCallback(
    (event: ReactPointerEvent<HTMLDivElement>) => {
      if (!draggingRef.current) return;
      const next = computeRatio(
        orientation === "vertical" ? event.clientX : event.clientY,
      );
      if (next !== ratio) onRatioChange(next);
    },
    [computeRatio, onRatioChange, ratio, orientation],
  );

  const stopDrag = useCallback(
    (event: ReactPointerEvent<HTMLDivElement>) => {
      if (!draggingRef.current) return;
      draggingRef.current = false;
      const id = pointerIdRef.current;
      if (id !== null && event.currentTarget.hasPointerCapture(id)) {
        event.currentTarget.releasePointerCapture(id);
      }
      pointerIdRef.current = null;
    },
    [],
  );

  useEffect(() => {
    return () => {
      draggingRef.current = false;
      pointerIdRef.current = null;
    };
  }, []);

  const handleKeyDown = useCallback(
    (event: React.KeyboardEvent<HTMLDivElement>) => {
      const step = event.shiftKey ? 0.1 : 0.02;
      let next: number | null = null;
      if (orientation === "vertical") {
        if (event.key === "ArrowLeft") next = ratio - step;
        else if (event.key === "ArrowRight") next = ratio + step;
        else if (event.key === "Home") next = minRatio;
        else if (event.key === "End") next = maxRatio;
        else if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onReset();
          return;
        }
      } else {
        if (event.key === "ArrowUp") next = ratio - step;
        else if (event.key === "ArrowDown") next = ratio + step;
      }
      if (next === null) return;
      event.preventDefault();
      onRatioChange(Math.min(maxRatio, Math.max(minRatio, next)));
    },
    [orientation, ratio, minRatio, maxRatio, onRatioChange, onReset],
  );

  return (
    <div
      role="separator"
      tabIndex={0}
      aria-orientation={orientation === "vertical" ? "vertical" : "horizontal"}
      aria-label={ariaLabel}
      aria-valuenow={Math.round(ratio * 100)}
      aria-valuemin={Math.round(minRatio * 100)}
      aria-valuemax={Math.round(maxRatio * 100)}
      onPointerDown={handlePointerDown}
      onPointerMove={handlePointerMove}
      onPointerUp={stopDrag}
      onPointerCancel={stopDrag}
      onLostPointerCapture={stopDrag}
      onDoubleClick={onReset}
      onKeyDown={handleKeyDown}
      className={cn(
        "group relative shrink-0 touch-none select-none",
        orientation === "vertical"
          ? "w-1 cursor-col-resize hover:w-1.5"
          : "h-1 cursor-row-resize hover:h-1.5",
        "bg-gray-200 transition-[background-color,width] duration-150",
        "hover:bg-red-300 focus:bg-red-300 focus:outline-none",
        className,
      )}
    >
      <span
        aria-hidden
        className={cn(
          "pointer-events-none absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 rounded-full bg-gray-400 opacity-0 transition-opacity duration-150 group-hover:opacity-100 group-focus:opacity-100",
          orientation === "vertical" ? "h-8 w-0.5" : "h-0.5 w-8",
        )}
      />
    </div>
  );
}
