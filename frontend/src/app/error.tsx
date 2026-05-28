"use client";

import { useEffect } from "react";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("Global error:", error);
  }, [error]);

  return (
    <div className="flex h-screen items-center justify-center bg-gray-50">
      <div className="max-w-md rounded-lg border border-red-200 bg-white p-8 shadow-lg">
        <h2 className="mb-4 text-xl font-bold text-red-600">
          Something went wrong
        </h2>
        <p className="mb-4 text-sm text-gray-600">
          {error.message || "An unexpected error occurred"}
        </p>
        {error.digest && (
          <p className="mb-4 text-xs text-gray-400">Error ID: {error.digest}</p>
        )}
        <div className="flex gap-2">
          <button
            onClick={reset}
            className="rounded bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-700"
          >
            Try again
          </button>
          <button
            onClick={() => (window.location.href = "/")}
            className="rounded bg-gray-200 px-4 py-2 text-sm text-gray-700 hover:bg-gray-300"
          >
            Go home
          </button>
        </div>
      </div>
    </div>
  );
}
