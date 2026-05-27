"use client";

import { useState } from "react";

export default function LoginPage() {
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

            // 成功后刷新页面，触发 SSR 重新检查 auth 状态
            window.location.href = "/workspace";
        } catch (err) {
            setError(err instanceof Error ? err.message : "An error occurred");
        } finally {
            setIsLoading(false);
        }
    };

    return (
        <div className="flex min-h-screen items-center justify-center">
            <div className="w-full max-w-md space-y-6 rounded-lg border p-8">
                <h1 className="text-2xl font-bold text-center">
                    {mode === "login" ? "Sign In" : "Create Account"}
                </h1>

                <form onSubmit={handleSubmit} className="space-y-4">
                    {mode === "register" && (
                        <div>
                            <label htmlFor="fullName" className="block text-sm font-medium">
                                Full Name
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
                            Email
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
                            Password
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

                    {error && (
                        <p className="text-sm text-red-500">{error}</p>
                    )}

                    <button
                        type="submit"
                        disabled={isLoading}
                        className="w-full rounded bg-blue-600 py-2 text-white hover:bg-blue-700 disabled:opacity-50"
                    >
                        {isLoading
                            ? "Loading..."
                            : mode === "login"
                                ? "Sign In"
                                : "Create Account"}
                    </button>
                </form>

                <p className="text-center text-sm">
                    {mode === "login"
                        ? "Don't have an account? "
                        : "Already have an account? "}
                    <button
                        type="button"
                        onClick={() => setMode(mode === "login" ? "register" : "login")}
                        className="text-blue-600 hover:underline"
                    >
                        {mode === "login" ? "Register" : "Sign In"}
                    </button>
                </p>
            </div>
        </div>
    );
}
