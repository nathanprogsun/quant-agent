"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { HomePromptInput } from "@/components/workspace/HomePromptInput";
import { STRATEGY_TEMPLATE_CHIPS } from "@/data/strategy-template-chips";
import { useLoginModal } from "@/contexts/LoginModalContext";
import { useAuth } from "@/core/auth/AuthProvider";
import { useCreateThread } from "@/hooks/useThreads";

export function WorkspaceHome() {
  const router = useRouter();
  const { isAuthenticated } = useAuth();
  const { openLoginModal } = useLoginModal();
  const createThread = useCreateThread();
  const [chipPrefill, setChipPrefill] = useState<string | null>(null);

  const requireAuth = () => {
    if (!isAuthenticated) {
      openLoginModal();
      return false;
    }
    return true;
  };

  const handleSend = (content: string) => {
    if (!requireAuth()) return;

    createThread.mutate(
      { title: content.slice(0, 40) },
      {
        onSuccess: (thread) => {
          router.push(
            `/workspace/chats/${thread.id}?initialMessage=${encodeURIComponent(content)}`,
          );
        },
      },
    );
  };

  const handleChipClick = (prompt: string) => {
    setChipPrefill(prompt);
  };

  return (
    <div className="flex h-full flex-col items-center justify-center px-6 py-8">
      <h1 className="text-3xl font-medium tracking-tight text-gray-900">
        JoinQuant人工智能投研平台
      </h1>
      <p className="mt-1 text-gray-500">智能投研 Quant Agent</p>

      <div className="mt-8 w-full flex flex-col items-center">
        <HomePromptInput
          onSend={handleSend}
          disabled={createThread.isPending}
          prefill={chipPrefill}
          onPrefillApplied={() => setChipPrefill(null)}
          className="w-full max-w-3xl"
        />

        <div className="mt-4 flex max-w-2xl flex-wrap justify-center gap-2">
          {STRATEGY_TEMPLATE_CHIPS.map((chip) => (
            <button
              key={chip.label}
              type="button"
              onClick={() => handleChipClick(chip.prompt)}
              className="rounded-full border border-gray-200 bg-white px-3 py-1.5 text-sm text-gray-700 hover:border-red-300 hover:bg-red-50"
            >
              {chip.label}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
