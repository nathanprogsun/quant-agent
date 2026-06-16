"use client";

export function WorkspaceTopBar() {
  return (
    <header className="flex h-12 shrink-0 items-center justify-between border-b bg-white px-4">
      <div className="flex items-center gap-2">
        <div
          className="flex size-7 items-center justify-center rounded-full bg-red-500 text-xs font-bold text-white"
          aria-hidden
        >
          Q
        </div>
        <span className="font-semibold text-gray-900">QuantAgent</span>
      </div>
      <p className="text-xs text-gray-500">智能投研 Quant Agent</p>
    </header>
  );
}
