"use client";

import { LoginForm } from "@/components/auth/LoginForm";

export default function LoginPage() {
  const handleSuccess = () => {
    window.location.href = "/workspace";
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-50 p-4">
      <div className="w-full max-w-md rounded-lg border bg-white p-8 shadow-sm">
        <LoginForm onSuccess={handleSuccess} />
      </div>
    </div>
  );
}
