"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { useUpdateThread } from "@/hooks/useThreads";

interface ThreadTitleProps {
  threadId: string;
  title: string | null;
}

export function ThreadTitle({ threadId, title }: ThreadTitleProps) {
  const [isEditing, setIsEditing] = useState(false);
  const [editValue, setEditValue] = useState(title ?? "");
  const inputRef = useRef<HTMLInputElement>(null);
  const updateThread = useUpdateThread();

  useEffect(() => {
    if (isEditing && inputRef.current) {
      inputRef.current.focus();
      inputRef.current.select();
    }
  }, [isEditing]);

  const handleSubmit = useCallback(() => {
    const trimmed = editValue.trim();
    if (trimmed && trimmed !== title) {
      updateThread.mutate({
        threadId,
        params: { title: trimmed },
      });
    }
    setIsEditing(false);
  }, [editValue, title, threadId, updateThread]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") {
      handleSubmit();
    } else if (e.key === "Escape") {
      setEditValue(title ?? "");
      setIsEditing(false);
    }
  };

  if (isEditing) {
    return (
      <input
        ref={inputRef}
        value={editValue}
        onChange={(e) => setEditValue(e.target.value)}
        onBlur={handleSubmit}
        onKeyDown={handleKeyDown}
        className="w-full rounded border px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
      />
    );
  }

  return (
    <h1
      onClick={() => setIsEditing(true)}
      className="cursor-pointer truncate text-lg font-semibold hover:text-blue-600"
      title="Click to edit"
    >
      {title ?? "Untitled Chat"}
    </h1>
  );
}
