import type { Message } from "@langchain/langgraph-sdk";
import { describe, expect, test } from "vitest";

import { mergeIncremental, mergeMessages } from "@/core/messages/merge";

describe("mergeMessages", () => {
  test("merges history, stream, and optimistic messages", () => {
    const history = [
      { id: "h1", type: "human", content: "Hello" },
    ] as Message[];
    const stream = [
      { id: "a1", type: "ai", content: "Hi" },
    ] as Message[];
    const optimistic = [
      { id: "opt1", type: "human", content: "New msg" },
    ] as Message[];

    const result = mergeMessages(history, stream, optimistic);

    expect(result).toHaveLength(3);
    expect(result[0].id).toBe("h1");
    expect(result[1].id).toBe("a1");
    expect(result[2].id).toBe("opt1");
  });

  test("stream messages override history with same id", () => {
    const history = [
      { id: "msg1", type: "ai", content: "old" },
    ] as Message[];
    const stream = [
      { id: "msg1", type: "ai", content: "new" },
    ] as Message[];

    const result = mergeMessages(history, stream, []);

    expect(result).toHaveLength(1);
    expect(result[0].content).toBe("new");
  });

  test("optimistic messages override stream with same id", () => {
    const stream = [
      { id: "msg1", type: "human", content: "from stream" },
    ] as Message[];
    const optimistic = [
      { id: "msg1", type: "human", content: "from optimistic" },
    ] as Message[];

    const result = mergeMessages([], stream, optimistic);

    expect(result).toHaveLength(1);
    expect(result[0].content).toBe("from optimistic");
  });

  test("deduplicates tool messages by tool_call_id when id is missing", () => {
    const history = [
      {
        type: "tool",
        tool_call_id: "call-1",
        content: "old",
      },
    ] as Message[];
    const stream = [
      {
        type: "tool",
        tool_call_id: "call-1",
        content: "new",
      },
    ] as Message[];

    const result = mergeMessages(history, stream, []);

    expect(result).toHaveLength(1);
    expect(result[0].content).toBe("new");
  });

  test("returns empty array when all inputs empty", () => {
    expect(mergeMessages([], [], [])).toEqual([]);
  });
});

describe("mergeIncremental", () => {
  test("appends new messages to existing", () => {
    const existing = [
      { id: "1", type: "human", content: "a" },
    ] as Message[];
    const incoming = [
      { id: "2", type: "ai", content: "b" },
    ] as Message[];

    const result = mergeIncremental(existing, incoming);

    expect(result).toHaveLength(2);
  });

  test("skips messages already in existing by id", () => {
    const existing = [
      { id: "1", type: "human", content: "a" },
    ] as Message[];
    const incoming = [
      { id: "1", type: "human", content: "updated" },
      { id: "2", type: "ai", content: "b" },
    ] as Message[];

    const result = mergeIncremental(existing, incoming);

    expect(result).toHaveLength(2);
    expect(result[0].content).toBe("a"); // original kept
    expect(result[1].content).toBe("b"); // new appended
  });

  test("returns existing when incoming is empty", () => {
    const existing = [
      { id: "1", type: "human", content: "a" },
    ] as Message[];

    expect(mergeIncremental(existing, [])).toBe(existing);
  });

  test("returns incoming when existing is empty", () => {
    const incoming = [
      { id: "1", type: "human", content: "a" },
    ] as Message[];

    expect(mergeIncremental([], incoming)).toBe(incoming);
  });
});
