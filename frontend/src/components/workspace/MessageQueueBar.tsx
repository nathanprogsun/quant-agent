"use client";

import {
  ChevronDown,
  ChevronUp,
  Pencil,
  SendHorizontal,
  X,
} from "lucide-react";
import { useState } from "react";

export interface QueuedMessageItem {
  id: string;
  content: string;
}

interface MessageQueueBarProps {
  items: QueuedMessageItem[];
  onRemove: (id: string) => void;
  onMoveUp: (id: string) => void;
  onMoveDown: (id: string) => void;
  onEdit: (id: string, content: string) => void;
  onSendNow: (id: string) => void;
  paused?: boolean;
}

function previewText(text: string, max = 120): string {
  const oneLine = text.replace(/\s+/g, " ").trim();
  if (oneLine.length <= max) return oneLine;
  return `${oneLine.slice(0, max)}…`;
}

export function MessageQueueBar({
  items,
  onRemove,
  onMoveUp,
  onMoveDown,
  onEdit,
  onSendNow,
  paused,
}: MessageQueueBarProps) {
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editDraft, setEditDraft] = useState("");

  if (items.length === 0) return null;

  const startEdit = (item: QueuedMessageItem) => {
    setEditingId(item.id);
    setEditDraft(item.content);
  };

  const commitEdit = (id: string) => {
    const trimmed = editDraft.trim();
    if (trimmed) onEdit(id, trimmed);
    setEditingId(null);
    setEditDraft("");
  };

  return (
    <div
      className="mb-3 rounded-xl border border-dashed border-gray-200 bg-gray-50/80 px-3 py-2"
      data-testid="message-queue-bar"
    >
      <div className="mb-2 flex items-center justify-between gap-2">
        <p className="text-xs font-medium text-gray-600">
          {items.length} 条待发送
          {paused ? (
            <span className="ml-2 text-amber-600">（队列已暂停，修复错误后继续）</span>
          ) : null}
        </p>
      </div>
      <ul className="space-y-2">
        {items.map((item, index) => (
          <li
            key={item.id}
            className="rounded-lg border border-gray-100 bg-white px-3 py-2"
          >
            <div className="flex items-start gap-2">
              <span className="mt-0.5 text-xs font-medium text-gray-400">
                {index + 1}
              </span>
              <div className="min-w-0 flex-1">
                {editingId === item.id ? (
                  <textarea
                    value={editDraft}
                    onChange={(e) => setEditDraft(e.target.value)}
                    rows={2}
                    className="w-full resize-none rounded border border-gray-200 px-2 py-1 text-sm outline-none focus:border-gray-300"
                  />
                ) : (
                  <p className="text-sm text-gray-700">
                    {previewText(item.content)}
                  </p>
                )}
              </div>
              <div className="flex shrink-0 items-center gap-0.5">
                {editingId === item.id ? (
                  <button
                    type="button"
                    className="rounded p-1 text-xs text-gray-600 hover:bg-gray-100"
                    onClick={() => commitEdit(item.id)}
                  >
                    保存
                  </button>
                ) : (
                  <>
                    <button
                      type="button"
                      aria-label="上移"
                      disabled={index === 0}
                      className="rounded p-1 text-gray-400 hover:bg-gray-100 disabled:opacity-30"
                      onClick={() => onMoveUp(item.id)}
                    >
                      <ChevronUp className="size-4" />
                    </button>
                    <button
                      type="button"
                      aria-label="下移"
                      disabled={index === items.length - 1}
                      className="rounded p-1 text-gray-400 hover:bg-gray-100 disabled:opacity-30"
                      onClick={() => onMoveDown(item.id)}
                    >
                      <ChevronDown className="size-4" />
                    </button>
                    <button
                      type="button"
                      aria-label="编辑"
                      className="rounded p-1 text-gray-400 hover:bg-gray-100"
                      onClick={() => startEdit(item)}
                    >
                      <Pencil className="size-3.5" />
                    </button>
                    <button
                      type="button"
                      aria-label="立即发送"
                      className="rounded p-1 text-gray-400 hover:bg-gray-100"
                      onClick={() => onSendNow(item.id)}
                    >
                      <SendHorizontal className="size-3.5" />
                    </button>
                    <button
                      type="button"
                      aria-label="移除"
                      className="rounded p-1 text-gray-400 hover:bg-gray-100"
                      onClick={() => onRemove(item.id)}
                    >
                      <X className="size-3.5" />
                    </button>
                  </>
                )}
              </div>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
