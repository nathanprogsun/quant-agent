"use client";

export function WorkspaceTopBar() {
  return (
    <header className="flex h-12 shrink-0 items-center justify-between border-b bg-white px-4">
      <div className="flex items-center gap-2">
        <svg
          viewBox="0 0 32 32"
          aria-hidden
          className="size-7 rounded-md"
        >
          <defs>
            <linearGradient
              id="qa-topbar-gradient"
              x1="0"
              y1="0"
              x2="32"
              y2="32"
              gradientUnits="userSpaceOnUse"
            >
              <stop offset="0" stopColor="#dc2626" />
              <stop offset="1" stopColor="#ef4444" />
            </linearGradient>
          </defs>
          <rect
            x="0"
            y="0"
            width="32"
            height="32"
            rx="6"
            fill="url(#qa-topbar-gradient)"
          />
          <path
            d="M22.4 22.4 19.6 19.6 M11 9 a6 6 0 1 0 5 9.6"
            stroke="#ffffff"
            strokeWidth={2.4}
            strokeLinecap="round"
            fill="none"
          />
        </svg>
        <span className="font-semibold text-gray-900">QuantAgent</span>
      </div>
      <p className="text-xs text-gray-500">智能投研 Quant Agent</p>
    </header>
  );
}
