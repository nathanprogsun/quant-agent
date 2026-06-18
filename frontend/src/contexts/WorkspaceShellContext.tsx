"use client";

import { createContext, useContext } from "react";

export type WorkspaceShellContextValue = {
  sidebarExpanded: boolean;
  openSidebar: () => void;
  closeSidebar: () => void;
  handleNewChat: () => void;
  isChatPage: boolean;
};

export const WorkspaceShellContext =
  createContext<WorkspaceShellContextValue | null>(null);

export function useWorkspaceShell() {
  const ctx = useContext(WorkspaceShellContext);
  if (!ctx) {
    throw new Error("useWorkspaceShell must be used within WorkspaceShell");
  }
  return ctx;
}
