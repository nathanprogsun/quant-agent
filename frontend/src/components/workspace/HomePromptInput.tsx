"use client";

import { ChevronDown, Paperclip, Square } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

interface HomePromptInputProps {
  onSend: (content: string) => void;
  onStop?: () => void;
  disabled?: boolean;
  isStreaming?: boolean;
  placeholder?: string;
  prefill?: string | null;
  onPrefillApplied?: () => void;
  showDisclaimer?: boolean;
  variant?: "default" | "chat";
  className?: string;
}

export function HomePromptInput({
  onSend,
  onStop,
  disabled,
  isStreaming = false,
  placeholder = "请输入您的策略想法 (Shift + Enter换行)",
  prefill,
  onPrefillApplied,
  showDisclaimer = false,
  variant = "default",
  className,
}: HomePromptInputProps) {
  const [input, setInput] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (!prefill) return;
    setInput(prefill);
    textareaRef.current?.focus();
    onPrefillApplied?.();
  }, [prefill, onPrefillApplied]);

  const handleSubmit = useCallback(() => {
    const trimmed = input.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setInput("");
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
  }, [disabled, input, onSend]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const handleChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value);
    const textarea = e.target;
    textarea.style.height = "auto";
    textarea.style.height = `${Math.min(textarea.scrollHeight, 200)}px`;
  };

  const shellClass =
    variant === "chat"
      ? "rounded-2xl border border-gray-200 bg-white p-4 shadow-[0_1px_8px_rgba(0,0,0,0.06)]"
      : "rounded-2xl border border-gray-200 bg-white p-4 shadow-sm";

  return (
    <div className={className}>
      <div className={shellClass}>
        <textarea
          ref={textareaRef}
          value={input}
          onChange={handleChange}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          disabled={disabled}
          rows={3}
          className="min-h-[88px] w-full resize-none text-sm text-gray-900 outline-none placeholder:text-gray-400"
        />
        <div className="mt-2 flex items-center justify-between">
          <button
            type="button"
            className="rounded p-2 text-gray-400 hover:bg-gray-100"
            aria-label="附件"
            disabled={disabled}
          >
            <Paperclip className="size-4" />
          </button>
          <div className="flex items-center gap-2">
            <button
              type="button"
              className="flex items-center gap-1 rounded-full border border-gray-200 px-3 py-1.5 text-xs text-gray-600"
              aria-label="智能体"
              disabled={disabled}
            >
              智能体
              <ChevronDown className="size-3.5 text-gray-400" />
            </button>
            {isStreaming ? (
              <button
                type="button"
                onClick={onStop}
                disabled={!onStop}
                className="flex size-9 items-center justify-center rounded-md bg-red-500 text-white hover:bg-red-600 disabled:cursor-not-allowed disabled:opacity-40"
                aria-label="停止生成"
              >
                <Square className="size-3.5 fill-current" />
              </button>
            ) : (
              <button
                type="button"
                onClick={handleSubmit}
                disabled={disabled || !input.trim()}
                className="flex size-9 items-center justify-center rounded-full bg-[#e8e8e8] text-gray-700 hover:bg-[#dcdcdc] disabled:cursor-not-allowed disabled:opacity-40"
                aria-label="发送"
              >
                <span className="text-base leading-none">↑</span>
              </button>
            )}
          </div>
        </div>
      </div>
      {showDisclaimer ? (
        <p className="mt-2 text-center text-xs text-gray-400">
          内容由 AI 生成，请仔细甄别
        </p>
      ) : null}
    </div>
  );
}
