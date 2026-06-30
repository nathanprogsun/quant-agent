"use client";

import { ChevronDown, Paperclip, Square } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { useSkills } from "@/core/skills";
import { applySkillSuggestion, getMatchingSkillSuggestions } from "@/core/skills/suggestions";

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
  const [activeSuggestion, setActiveSuggestion] = useState(0);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const { skills } = useSkills();

  useEffect(() => {
    if (!prefill) return;
    setInput(prefill);
    textareaRef.current?.focus();
    onPrefillApplied?.();
  }, [prefill, onPrefillApplied]);

  const slashPrefix = useMemo(() => extractSlashPrefix(input), [input]);
  const suggestions = useMemo(
    () => (slashPrefix !== null ? getMatchingSkillSuggestions(slashPrefix, skills) : []),
    [slashPrefix, skills],
  );

  useEffect(() => {
    // Reset active index whenever the suggestion set changes
    setActiveSuggestion(0);
  }, [suggestions.length]);

  const handleSubmit = useCallback(() => {
    const trimmed = input.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setInput("");
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
  }, [disabled, input, onSend]);

  const acceptSuggestion = useCallback(
    (index: number) => {
      const skill = suggestions[index];
      if (!skill) return;
      const next = applySkillSuggestion(input, skill.name);
      setInput(next);
      textareaRef.current?.focus();
    },
    [input, suggestions],
  );

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (suggestions.length > 0) {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setActiveSuggestion((i) => (i + 1) % suggestions.length);
        return;
      }
      if (e.key === "ArrowUp") {
        e.preventDefault();
        setActiveSuggestion((i) => (i - 1 + suggestions.length) % suggestions.length);
        return;
      }
      if (e.key === "Enter" || e.key === "Tab") {
        e.preventDefault();
        acceptSuggestion(activeSuggestion);
        return;
      }
      if (e.key === "Escape") {
        e.preventDefault();
        return;
      }
    }
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
        {suggestions.length > 0 ? (
          <ul
            role="listbox"
            aria-label="技能建议"
            className="mt-1 max-h-48 overflow-auto rounded border border-gray-200 bg-white py-1 text-sm"
          >
            {suggestions.map((skill, index) => (
              <li
                key={skill.name}
                role="option"
                aria-selected={index === activeSuggestion}
                onMouseDown={(e) => {
                  e.preventDefault();
                  acceptSuggestion(index);
                }}
                onMouseEnter={() => setActiveSuggestion(index)}
                className={`cursor-pointer px-3 py-1.5 ${
                  index === activeSuggestion ? "bg-blue-50" : ""
                }`}
              >
                <span className="font-mono text-blue-600">/{skill.name}</span>
                <span className="ml-2 text-gray-500">{skill.description}</span>
              </li>
            ))}
          </ul>
        ) : null}
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

/**
 * Extract the slash-command prefix at the end of the input.
 *
 * Returns the text after a leading `/` when the input ends with `/<token>` and
 * the token contains no whitespace; otherwise null (no active slash command).
 */
function extractSlashPrefix(input: string): string | null {
  const match = /\/([a-zA-Z0-9_-]*)$/.exec(input);
  if (!match) return null;
  return match[1];
}
