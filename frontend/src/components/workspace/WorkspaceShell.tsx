"use client";

import { PanelLeft, Plus } from "lucide-react";
import { usePathname, useRouter } from "next/navigation";
import { useState } from "react";

import { LoginModal } from "@/components/auth/LoginModal";
import { ThreadList } from "@/components/workspace/ThreadList";
import { QuantAgentShell } from "@/components/workspace/QuantAgentShell";
import { WorkspaceTopBar } from "@/components/workspace/WorkspaceTopBar";
import { LoginModalProvider, useLoginModal } from "@/contexts/LoginModalContext";
import { WorkspaceShellContext } from "@/contexts/WorkspaceShellContext";
import { useAuth } from "@/core/auth/AuthProvider";

interface WorkspaceShellProps {
  children: React.ReactNode;
}

function SidebarToggle({
  onClick,
  className = "",
}: {
  onClick: () => void;
  className?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded-md p-1.5 text-gray-600 hover:bg-black/5 ${className}`}
      aria-label="切换侧栏"
    >
      <PanelLeft className="size-4" />
    </button>
  );
}

function WorkspaceShellInner({ children }: WorkspaceShellProps) {
  const router = useRouter();
  const pathname = usePathname();
  const { user } = useAuth();
  const [sidebarExpanded, setSidebarExpanded] = useState(false);

  const isGuestView = !user;
  const isChatPage = pathname.startsWith("/workspace/chats/");
  const showSidebarHistory = !isGuestView;

  const handleNewChat = () => {
    setSidebarExpanded(true);
    router.push("/workspace");
  };

  const shellContext = {
    sidebarExpanded,
    openSidebar: () => setSidebarExpanded(true),
    closeSidebar: () => setSidebarExpanded(false),
    handleNewChat,
    isChatPage,
  };

  return (
    <WorkspaceShellContext.Provider value={shellContext}>
      <div className="flex h-screen flex-col bg-white text-gray-900">
      <WorkspaceTopBar />

      <div className="flex min-h-0 flex-1">
        {sidebarExpanded ? (
          <aside
            className={`flex w-[240px] shrink-0 flex-col border-r border-gray-200 bg-white px-4 py-3 min-h-0`}
          >
            <div className="flex h-9 shrink-0 items-center justify-between">
              <SidebarToggle onClick={() => setSidebarExpanded(false)} />
              <button
                type="button"
                onClick={handleNewChat}
                className="rounded-md p-1.5 text-gray-600 hover:bg-black/5"
                aria-label="新对话"
              >
                <Plus className="size-4" />
              </button>
            </div>

            <div className="mt-2 flex min-h-0 flex-1 flex-col overflow-auto">
              <ThreadList showHistory={showSidebarHistory} />
            </div>
          </aside>
        ) : null}

        <main className="relative flex min-w-0 flex-1 flex-col overflow-hidden">
          {!sidebarExpanded && !isChatPage ? (
            <SidebarToggle
              onClick={() => setSidebarExpanded(true)}
              className="absolute left-3 top-3 z-10"
            />
          ) : null}

          <QuantAgentShell>{children}</QuantAgentShell>
        </main>
      </div>

      <LoginModal />
      </div>
    </WorkspaceShellContext.Provider>
  );
}

export function WorkspaceShell({ children }: WorkspaceShellProps) {
  return (
    <LoginModalProvider>
      <WorkspaceShellInner>{children}</WorkspaceShellInner>
    </LoginModalProvider>
  );
}
