import { expect, test } from "vitest";

import { sanitizeRunStreamOptions } from "@/core/api/stream-mode";

test("drops unsupported stream modes from array payloads", () => {
  const sanitized = sanitizeRunStreamOptions({
    streamMode: ["values", "messages-tuple", "custom", "updates", "events", "tools"],
  });

  expect(sanitized.streamMode).toEqual([
    "values",
    "messages-tuple",
    "custom",
    "updates",
    "events",
  ]);
});

test("drops unsupported stream modes from scalar payloads", () => {
  const sanitized = sanitizeRunStreamOptions({
    streamMode: "tools",
  });

  expect(sanitized.streamMode).toBeUndefined();
});

test("keeps supported scalar stream mode unchanged", () => {
  const sanitized = sanitizeRunStreamOptions({
    streamMode: "values",
  });

  expect(sanitized.streamMode).toBe("values");
});

test("keeps payloads without streamMode untouched", () => {
  const options = {
    streamSubgraphs: true,
  };

  expect(sanitizeRunStreamOptions(options)).toBe(options);
});

test("maps LangGraph continue disconnect mode to keep_alive", () => {
  const sanitized = sanitizeRunStreamOptions({
    onDisconnect: "continue",
    streamMode: ["values"],
  });

  expect(sanitized.onDisconnect).toBe("keep_alive");
});

test("handles null payload", () => {
  expect(sanitizeRunStreamOptions(null)).toBeNull();
});

test("handles non-object payload", () => {
  expect(sanitizeRunStreamOptions("string")).toBe("string");
  expect(sanitizeRunStreamOptions(42)).toBe(42);
});
