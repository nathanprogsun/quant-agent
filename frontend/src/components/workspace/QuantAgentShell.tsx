"use client";

import type { ReactNode } from "react";

interface QuantAgentShellProps {
  guest?: boolean;
  children: ReactNode;
}

export function QuantAgentShell({ guest = false, children }: QuantAgentShellProps) {
  return (
    <div className="relative min-h-0 flex-1">
      <div
        className={
          guest
            ? "pointer-events-none min-h-full select-none blur-sm opacity-80"
            : "min-h-full"
        }
      >
        {children}
      </div>
      {guest ? (
        <div
          className="pointer-events-none absolute inset-0 bg-white/30"
          aria-hidden
        />
      ) : null}
    </div>
  );
}
