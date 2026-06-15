"use client";

import { LoginForm } from "@/components/auth/LoginForm";
import { useLoginModal } from "@/contexts/LoginModalContext";
import { useAuth } from "@/core/auth/AuthProvider";

export function LoginModal() {
  const { isOpen, closeLoginModal } = useLoginModal();
  const { syncAuth } = useAuth();

  if (!isOpen) return null;

  const handleSuccess = async () => {
    await syncAuth();
    closeLoginModal();
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      role="dialog"
      aria-modal="true"
      aria-label="登录"
    >
      <div className="relative w-full max-w-md rounded-lg border bg-white p-8 shadow-xl">
        <button
          type="button"
          onClick={closeLoginModal}
          className="absolute right-3 top-3 text-gray-400 hover:text-gray-600"
          aria-label="关闭"
        >
          ×
        </button>
        <LoginForm onSuccess={handleSuccess} />
      </div>
    </div>
  );
}
