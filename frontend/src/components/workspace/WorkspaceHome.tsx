"use client";

import { useRouter } from "next/navigation";

import { InputBox } from "@/components/workspace/InputBox";
import { useLoginModal } from "@/contexts/LoginModalContext";
import { useAuth } from "@/core/auth/AuthProvider";
import { useCreateThread } from "@/hooks/useThreads";

export function WorkspaceHome() {
  const router = useRouter();
  const { isAuthenticated } = useAuth();
  const { openLoginModal } = useLoginModal();
  const createThread = useCreateThread();

  const handleSend = (content: string) => {
    if (!isAuthenticated) {
      openLoginModal();
      return;
    }

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

  return (
    <div className="flex h-full flex-col items-center justify-center px-6">
      <div className="w-full max-w-2xl text-center">
        <h1 className="text-3xl font-bold tracking-tight text-gray-900">
          Quant Agent
        </h1>
        <p className="mt-2 text-gray-500">
          用自然语言描述你的量化策略，AI 帮你生成代码并回测
        </p>
        <div className="mt-8 rounded-xl border bg-white shadow-sm">
          <InputBox
            onSend={handleSend}
            disabled={createThread.isPending}
            placeholder="描述你想实现的策略，例如：小市值轮动策略…"
            className="border-0"
          />
        </div>
      </div>
    </div>
  );
}
