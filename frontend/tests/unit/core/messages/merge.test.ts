import type { Message } from "@langchain/langgraph-sdk";
import { describe, expect, test } from "vitest";

import {
  filterConfirmedOptimistic,
  mergeIncremental,
  mergeMessages,
  normalizeCheckpointMessage,
} from "@/core/messages/merge";

describe("mergeMessages", () => {
  test("prefers stream over history when stream is hydrated", () => {
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

    expect(result).toHaveLength(2);
    expect(result[0].id).toBe("a1");
    expect(result[1].id).toBe("opt1");
  });

  test("uses normalized history before stream hydration", () => {
    const history = [
      {
        type: "human",
        data: { content: "Hello", id: "h1" },
      },
    ] as unknown as Message[];

    const result = mergeMessages(history, [], []);

    expect(result).toHaveLength(1);
    expect(result[0].content).toBe("Hello");
    expect(result[0].id).toBe("h1");
  });

  test("does not duplicate the same conversation from history and stream", () => {
    const history = [
      { type: "human", data: { content: "hi", id: "hist-human" } },
      { type: "ai", data: { content: "Hello there", id: "hist-ai" } },
    ] as unknown as Message[];
    const stream = [
      { id: "stream-human", type: "human", content: "hi" },
      { id: "stream-ai", type: "ai", content: "Hello there" },
    ] as Message[];

    const result = mergeMessages(history, stream, []);

    expect(result).toHaveLength(2);
    expect(result[0].id).toBe("stream-human");
    expect(result[1].id).toBe("stream-ai");
  });

  test("optimistic messages append on top of stream", () => {
    const stream = [
      { id: "msg1", type: "human", content: "from stream" },
    ] as Message[];
    const optimistic = [
      { id: "opt1", type: "human", content: "pending" },
    ] as Message[];

    const result = mergeMessages([], stream, optimistic);

    expect(result).toHaveLength(2);
    expect(result[1].content).toBe("pending");
  });

  test("returns empty array when all inputs empty", () => {
    expect(mergeMessages([], [], [])).toEqual([]);
  });
});

describe("normalizeCheckpointMessage", () => {
  test("promotes data.content to top-level content", () => {
    const message = {
      type: "human",
      data: { content: "hello", id: "m1" },
    } as unknown as Message;

    const normalized = normalizeCheckpointMessage(message);

    expect(normalized.content).toBe("hello");
    expect(normalized.id).toBe("m1");
  });
});

describe("filterConfirmedOptimistic", () => {
  test("drops optimistic human when stream already has same content", () => {
    const stream = [
      { id: "real-1", type: "human", content: "hi" },
    ] as Message[];
    const optimistic = [
      { id: "optimistic-1", type: "human", content: "hi" },
    ] as Message[];

    expect(filterConfirmedOptimistic(stream, optimistic)).toEqual([]);
  });

  test("keeps optimistic human until stream confirms", () => {
    const stream = [{ id: "a1", type: "ai", content: "..." }] as Message[];
    const optimistic = [
      { id: "optimistic-1", type: "human", content: "hi" },
    ] as Message[];

    expect(filterConfirmedOptimistic(stream, optimistic)).toEqual(optimistic);
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
    expect(result[0].content).toBe("a");
    expect(result[1].content).toBe("b");
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
