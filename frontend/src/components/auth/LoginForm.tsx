"use client";

import { useState } from "react";

interface LoginFormProps {
  onSuccess?: () => void | Promise<void>;
  className?: string;
}

export function LoginForm({ onSuccess, className }: LoginFormProps) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setIsLoading(true);

    try {
      const endpoint =
        mode === "login" ? "/api/v1/auth/login" : "/api/v1/auth/register";
      const body =
        mode === "login"
          ? { email, password }
          : { email, password, full_name: fullName };

      const response = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify(body),
      });

      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.detail ?? "Authentication failed");
      }

      await onSuccess?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "An error occurred");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className={className}>
      <h2 className="text-center text-xl font-semibold">
        {mode === "login" ? "登录 Quant Agent" : "注册账号"}
      </h2>

      <form onSubmit={handleSubmit} className="mt-6 space-y-4">
        {mode === "register" && (
          <div>
            <label htmlFor="fullName" className="block text-sm font-medium">
              姓名
            </label>
            <input
              id="fullName"
              type="text"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              className="mt-1 w-full rounded border px-3 py-2"
              required
            />
          </div>
        )}

        <div>
          <label htmlFor="email" className="block text-sm font-medium">
            邮箱
          </label>
          <input
            id="email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="mt-1 w-full rounded border px-3 py-2"
            required
          />
        </div>

        <div>
          <label htmlFor="password" className="block text-sm font-medium">
            密码
          </label>
          <input
            id="password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="mt-1 w-full rounded border px-3 py-2"
            required
            minLength={8}
          />
        </div>

        {error ? <p className="text-sm text-red-500">{error}</p> : null}

        <button
          type="submit"
          disabled={isLoading}
          className="w-full rounded bg-red-600 py-2.5 font-medium text-white hover:bg-red-700 disabled:opacity-50"
        >
          {isLoading
            ? "处理中..."
            : mode === "login"
              ? "登录"
              : "注册"}
        </button>
      </form>

      <p className="mt-4 text-center text-sm text-gray-600">
        {mode === "login" ? "还没有账号？" : "已有账号？"}
        <button
          type="button"
          onClick={() => setMode(mode === "login" ? "register" : "login")}
          className="ml-1 text-red-600 hover:underline"
        >
          {mode === "login" ? "注册" : "登录"}
        </button>
      </p>
    </div>
  );
}
