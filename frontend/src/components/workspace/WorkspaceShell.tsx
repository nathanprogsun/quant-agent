"use client";

import { LoginModal } from "@/components/auth/LoginModal";
import { ThreadList } from "@/components/workspace/ThreadList";
import { QuantAgentShell } from "@/components/workspace/QuantAgentShell";
import { LoginModalProvider } from "@/contexts/LoginModalContext";
import { useAuth } from "@/core/auth/AuthProvider";

interface WorkspaceShellProps {
  isGuest: boolean;
  children: React.ReactNode;
}

export function WorkspaceShell({ isGuest, children }: WorkspaceShellProps) {
  const { user } = useAuth();

  return (
    <LoginModalProvider defaultOpen={isGuest}>
      <div className="grid h-screen grid-cols-[240px_minmax(0,1fr)]">
        <aside className="flex flex-col border-r bg-gray-50">
          <div className="border-b px-4 py-3">
            <h2 className="text-sm font-semibold text-gray-900">Quant Agent</h2>
          </div>
          <div className="flex-1 overflow-auto p-3">
            <ThreadList guest={isGuest} />
          </div>
        </aside>
        <main className="flex min-w-0 flex-col overflow-hidden">
          <QuantAgentShell guest={isGuest && !user}>{children}</QuantAgentShell>
        </main>
      </div>
      <LoginModal />
    </LoginModalProvider>
  );
}
