"use client";

import type { ReactNode } from "react";

interface QuantAgentShellProps {
  children: ReactNode;
}

export function QuantAgentShell({ children }: QuantAgentShellProps) {
  return <div className="min-h-0 flex-1">{children}</div>;
}
