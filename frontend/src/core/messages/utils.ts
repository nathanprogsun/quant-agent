import type { Message } from "@langchain/langgraph-sdk";

// ── Message Grouping ────────────────────────────────────────────────────────

interface MessageGroup {
  type: "human" | "assistant" | "tool";
  id: string | undefined;
  messages: Message[];
}

export function getMessageGroups(messages: Message[]): MessageGroup[] {
  if (messages.length === 0) return [];

  const groups: MessageGroup[] = [];

  for (const message of messages) {
    if (message.type === "human") {
      groups.push({ id: message.id, type: "human", messages: [message] });
      continue;
    }

    if (message.type === "tool") {
      // Tool messages attach to the preceding assistant group
      const lastGroup = groups[groups.length - 1];
      if (lastGroup && lastGroup.type === "assistant") {
        lastGroup.messages.push(message);
      } else {
        groups.push({ id: message.id, type: "tool", messages: [message] });
      }
      continue;
    }

    if (message.type === "ai") {
      // If AI message has tool_calls, start/extend an assistant group
      const hasToolCalls =
        "tool_calls" in message &&
        Array.isArray(message.tool_calls) &&
        message.tool_calls.length > 0;

      if (hasToolCalls) {
        const lastGroup = groups[groups.length - 1];
        if (lastGroup?.type === "assistant") {
          lastGroup.messages.push(message);
        } else {
          groups.push({
            id: message.id,
            type: "assistant",
            messages: [message],
          });
        }
      } else {
        // Final AI response — new group
        groups.push({
          id: message.id,
          type: "assistant",
          messages: [message],
        });
      }
    }
  }

  return groups;
}

// ── Content Extraction ──────────────────────────────────────────────────────

export function extractContentFromMessage(message: Message): string {
  if (typeof message.content === "string") {
    return message.content.trim();
  }
  if (Array.isArray(message.content)) {
    return message.content
      .map((part) => {
        if (typeof part === "string") return part;
        if ("text" in part) return part.text;
        return "";
      })
      .join("\n")
      .trim();
  }

  const data = (message as Message & { data?: { content?: unknown } }).data;
  if (data && typeof data.content === "string") {
    return data.content.trim();
  }
  if (data && Array.isArray(data.content)) {
    return data.content
      .map((part) => {
        if (typeof part === "string") return part;
        if (part && typeof part === "object" && "text" in part) {
          return String(part.text);
        }
        return "";
      })
      .join("\n")
      .trim();
  }

  return "";
}

// ── Tool Call Extraction ────────────────────────────────────────────────────

interface ToolCall {
  id: string;
  name: string;
  args: Record<string, unknown>;
}

export function extractToolCallsFromMessage(message: Message): ToolCall[] {
  if (!("tool_calls" in message) || !Array.isArray(message.tool_calls)) {
    return [];
  }
  return message.tool_calls.map((tc) => ({
    id: tc.id ?? "",
    name: tc.name ?? "unknown",
    args: (tc.args as Record<string, unknown>) ?? {},
  }));
}
