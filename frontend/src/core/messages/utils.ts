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

function textFromContentPart(part: unknown): string {
  if (typeof part === "string") return part;
  if (!part || typeof part !== "object") return "";

  const typed = part as { type?: string; text?: string; reasoning?: string };
  const blockType = typed.type;

  if (blockType === "reasoning" || blockType === "thinking") {
    return "";
  }

  if (blockType === "text" || blockType === undefined) {
    return typed.text ?? "";
  }

  if ("text" in typed && typeof typed.text === "string") {
    return typed.text;
  }

  return "";
}

function extractReasoningFromAdditionalKwargs(message: Message): string {
  const kwargs = (message as Message & {
    additional_kwargs?: Record<string, unknown>;
  }).additional_kwargs;
  if (!kwargs) return "";

  const reasoningContent = kwargs.reasoning_content;
  if (typeof reasoningContent === "string" && reasoningContent.trim()) {
    return reasoningContent.trim();
  }

  const reasoning = kwargs.reasoning;
  if (typeof reasoning === "string" && reasoning.trim()) {
    return reasoning.trim();
  }
  if (reasoning && typeof reasoning === "object") {
    const summary = (reasoning as { summary?: string }).summary;
    if (typeof summary === "string" && summary.trim()) {
      return summary.trim();
    }
  }

  return "";
}

export function extractReasoningFromMessage(message: Message): string {
  const parts: string[] = [];

  const kwargsReasoning = extractReasoningFromAdditionalKwargs(message);
  if (kwargsReasoning) parts.push(kwargsReasoning);

  if (typeof message.content === "string") {
    const { thinking } = splitThinkingFromText(message.content);
    if (thinking) parts.push(thinking);
  }

  if (Array.isArray(message.content)) {
    const blockReasoning = message.content
      .map((part) => {
        if (!part || typeof part !== "object") return "";
        const typed = part as {
          type?: string;
          text?: string;
          reasoning?: string;
          summary?: string;
        };
        const blockType = typed.type;
        if (blockType !== "reasoning" && blockType !== "thinking") return "";
        if (typeof typed.reasoning === "string" && typed.reasoning.trim()) {
          return typed.reasoning.trim();
        }
        if (typeof typed.summary === "string" && typed.summary.trim()) {
          return typed.summary.trim();
        }
        if (typeof typed.text === "string" && typed.text.trim()) {
          return typed.text.trim();
        }
        return "";
      })
      .filter(Boolean)
      .join("\n")
      .trim();
    if (blockReasoning) parts.push(blockReasoning);
  }

  return parts.join("\n\n").trim();
}

export function extractContentFromMessage(message: Message): string {
  if (typeof message.content === "string") {
    return splitThinkingFromText(message.content).text;
  }
  if (Array.isArray(message.content)) {
    return message.content
      .map((part) => textFromContentPart(part))
      .join("\n")
      .trim();
  }

  const data = (message as Message & { data?: { content?: unknown } }).data;
  if (data && typeof data.content === "string") {
    return splitThinkingFromText(data.content).text;
  }
  if (data && Array.isArray(data.content)) {
    return data.content
      .map((part) => textFromContentPart(part))
      .join("\n")
      .trim();
  }

  return "";
}

/** Split visible reply text from inline model thinking blocks. */
export function splitThinkingFromText(content: string): {
  thinking: string;
  text: string;
} {
  const thinkingParts: string[] = [];
  const captureThinking = (inner: string) => {
    if (inner.trim()) thinkingParts.push(inner.trim());
  };

  const thinkingTag = `(?:${"redacted_"}thinking|thinking)`;

  let withoutThinking = content.replace(
    new RegExp(`<${thinkingTag}>([\\s\\S]*?)<\\/${thinkingTag}>`, "gi"),
    (_, inner: string) => {
      captureThinking(inner);
      return "";
    },
  );

  // Streaming chunks may include an opening tag before the closing tag arrives.
  withoutThinking = withoutThinking.replace(
    new RegExp(`<${thinkingTag}>([\\s\\S]*)$`, "i"),
    (_, inner: string) => {
      captureThinking(inner);
      return "";
    },
  );

  withoutThinking = withoutThinking.replace(
    new RegExp(`<\\/?${thinkingTag}\\b[^>]*>`, "gi"),
    "",
  );

  let text = withoutThinking.trim();
  let thinking = thinkingParts.join("\n\n").trim();

  const sectionMatch = text.match(/\n(?=#{1,2}\s+[^\n]+)/);
  if (sectionMatch && sectionMatch.index !== undefined && sectionMatch.index > 40) {
    const preamble = text.slice(0, sectionMatch.index).trim();
    const body = text.slice(sectionMatch.index).trim();
    if (preamble && !preamble.startsWith("#")) {
      thinking = [thinking, preamble].filter(Boolean).join("\n\n");
      text = body;
    }
  }

  const greetingSplit = text.match(
    /^(?:用户问的是|用户想要|我需要根据|让我)[\s\S]*?(?=\n\n(?:#{1,2}\s|\*\*[^*]+\*\*|您好！|你好！))/,
  );
  if (greetingSplit && greetingSplit[0].length < text.length - 20) {
    thinking = [thinking, greetingSplit[0].trim()].filter(Boolean).join("\n\n");
    text = text.slice(greetingSplit[0].length).trim();
  }

  return { thinking, text };
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

/** Last AI message in the thread (includes tool-call rounds). */
export function getLastAiMessage(messages: Message[]): Message | undefined {
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    if (messages[i].type === "ai") return messages[i];
  }
  return undefined;
}

/** Last assistant message suitable for user-visible streaming (skips tool-call rounds). */
export function getLastVisibleAiMessage(messages: Message[]): Message | undefined {
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const message = messages[i];
    if (message.type !== "ai") continue;
    if (extractToolCallsFromMessage(message).length > 0) continue;
    return message;
  }
  return undefined;
}

export function aiMessageHasToolCalls(message: Message): boolean {
  return extractToolCallsFromMessage(message).length > 0;
}

export interface ThinkingToolStep {
  id: string;
  name: string;
  status: "running" | "done";
}

export function extractThinkingToolStepsFromMessages(
  messages: Message[],
): ThinkingToolStep[] {
  const steps: ThinkingToolStep[] = [];

  for (const message of messages) {
    if (message.type === "ai") {
      for (const toolCall of extractToolCallsFromMessage(message)) {
        steps.push({
          id: toolCall.id,
          name: toolCall.name,
          status: "running",
        });
      }
    }

    if (message.type === "tool" && "tool_call_id" in message) {
      const toolCallId =
        typeof message.tool_call_id === "string" ? message.tool_call_id : "";
      const step = steps.find((entry) => entry.id === toolCallId);
      if (step) step.status = "done";
    }
  }

  return steps;
}

export function getLastAssistantGroupMessages(messages: Message[]): Message[] {
  const groups = getMessageGroups(messages);
  const lastAssistant = groups.filter((group) => group.type === "assistant").pop();
  return lastAssistant?.messages ?? [];
}
