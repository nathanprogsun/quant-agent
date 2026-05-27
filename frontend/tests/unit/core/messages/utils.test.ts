import type { Message } from "@langchain/langgraph-sdk";
import { describe, expect, test } from "vitest";

import {
  extractContentFromMessage,
  extractToolCallsFromMessage,
  getMessageGroups,
} from "@/core/messages/utils";

describe("getMessageGroups", () => {
  test("groups human and assistant messages separately", () => {
    const messages = [
      { id: "h1", type: "human", content: "Hello" },
      { id: "a1", type: "ai", content: "Hi there" },
    ] as Message[];

    const groups = getMessageGroups(messages);

    expect(groups).toHaveLength(2);
    expect(groups[0].type).toBe("human");
    expect(groups[1].type).toBe("assistant");
  });

  test("groups AI message with tool_calls and its tool results together", () => {
    const messages = [
      {
        id: "a1",
        type: "ai",
        content: "",
        tool_calls: [{ id: "tc1", name: "search", args: {} }],
      },
      {
        id: "t1",
        type: "tool",
        tool_call_id: "tc1",
        content: "result",
      },
    ] as Message[];

    const groups = getMessageGroups(messages);

    expect(groups).toHaveLength(1);
    expect(groups[0].type).toBe("assistant");
    expect(groups[0].messages).toHaveLength(2);
  });

  test("final AI response gets its own group", () => {
    const messages = [
      {
        id: "a1",
        type: "ai",
        content: "",
        tool_calls: [{ id: "tc1", name: "search", args: {} }],
      },
      {
        id: "t1",
        type: "tool",
        tool_call_id: "tc1",
        content: "result",
      },
      { id: "a2", type: "ai", content: "Final answer" },
    ] as Message[];

    const groups = getMessageGroups(messages);

    // tool_calls group + final response group
    expect(groups).toHaveLength(2);
    expect(groups[0].type).toBe("assistant");
    expect(groups[0].messages).toHaveLength(2); // ai+tool_calls + tool result
    expect(groups[1].type).toBe("assistant");
    expect(groups[1].messages).toHaveLength(1); // final ai
  });

  test("returns empty array for empty input", () => {
    expect(getMessageGroups([])).toEqual([]);
  });

  test("handles standalone tool messages", () => {
    const messages = [
      { id: "t1", type: "tool", tool_call_id: "orphan", content: "data" },
    ] as Message[];

    const groups = getMessageGroups(messages);

    expect(groups).toHaveLength(1);
    expect(groups[0].type).toBe("tool");
  });

  test("separates consecutive AI messages without tool_calls", () => {
    const messages = [
      { id: "a1", type: "ai", content: "Part 1" },
      { id: "a2", type: "ai", content: "Part 2" },
    ] as Message[];

    const groups = getMessageGroups(messages);

    expect(groups).toHaveLength(2);
    expect(groups[0].type).toBe("assistant");
    expect(groups[1].type).toBe("assistant");
  });
});

describe("extractContentFromMessage", () => {
  test("extracts string content", () => {
    const message = { id: "1", type: "ai", content: "Hello world" } as Message;
    expect(extractContentFromMessage(message)).toBe("Hello world");
  });

  test("extracts array content", () => {
    const message = {
      id: "1",
      type: "ai",
      content: [
        { type: "text", text: "Part 1" },
        { type: "text", text: "Part 2" },
      ],
    } as unknown as Message;
    expect(extractContentFromMessage(message)).toBe("Part 1\nPart 2");
  });

  test("returns empty string for empty content", () => {
    const message = { id: "1", type: "ai", content: "" } as Message;
    expect(extractContentFromMessage(message)).toBe("");
  });

  test("trims whitespace", () => {
    const message = { id: "1", type: "ai", content: "  hello  " } as Message;
    expect(extractContentFromMessage(message)).toBe("hello");
  });
});

describe("extractToolCallsFromMessage", () => {
  test("extracts tool calls from AI message", () => {
    const message = {
      id: "a1",
      type: "ai",
      content: "",
      tool_calls: [
        { id: "tc1", name: "search", args: { query: "test" } },
        { id: "tc2", name: "bash", args: { command: "ls" } },
      ],
    } as Message;

    const toolCalls = extractToolCallsFromMessage(message);

    expect(toolCalls).toHaveLength(2);
    expect(toolCalls[0].name).toBe("search");
    expect(toolCalls[1].name).toBe("bash");
  });

  test("returns empty array for message without tool_calls", () => {
    const message = { id: "a1", type: "ai", content: "text" } as Message;
    expect(extractToolCallsFromMessage(message)).toEqual([]);
  });

  test("returns empty array for human messages", () => {
    const message = { id: "h1", type: "human", content: "text" } as Message;
    expect(extractToolCallsFromMessage(message)).toEqual([]);
  });
});
