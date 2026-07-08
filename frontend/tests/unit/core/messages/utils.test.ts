import type { Message } from "@langchain/langgraph-sdk";
import { describe, expect, test } from "vitest";

import {
  convertToCoTSteps,
  extractContentFromMessage,
  extractReasoningFromMessage,
  extractReasoningSegmentsFromMessages,
  extractToolCallsFromMessage,
  getLastAiMessage,
  getLastVisibleAiMessage,
  getMessageGroups,
  splitThinkingFromText,
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

  test("strips inline redacted_thinking from string content", () => {
    const open = "<thinking>";
    const close = "</thinking>";
    const message = {
      id: "1",
      type: "ai",
      content: `${open}plan${close}\n\n## Answer\n\nHi`,
    } as Message;
    expect(extractContentFromMessage(message)).toBe("## Answer\n\nHi");
  });

  test("extracts LangChain checkpoint data.content string", () => {
    const message = {
      type: "human",
      data: { content: "hi", id: "msg-1" },
    } as unknown as Message;
    expect(extractContentFromMessage(message)).toBe("hi");
  });

  test("extracts LangChain checkpoint data.content array", () => {
    const message = {
      type: "ai",
      data: {
        content: [{ type: "text", text: "Hello" }],
      },
    } as unknown as Message;
    expect(extractContentFromMessage(message)).toBe("Hello");
  });
});

describe("splitThinkingFromText", () => {
  test("strips redacted_thinking tags", () => {
    const open = "<thinking>";
    const close = "</thinking>";
    const { thinking, text } = splitThinkingFromText(
      `${open}inner${close}\n\n## Title\n\nBody`,
    );
    expect(thinking).toBe("inner");
    expect(text).toBe("## Title\n\nBody");
  });

  test("splits Chinese reasoning preamble before markdown heading", () => {
    const raw =
      "用户问的是'ETF轮动策略'，我需要根据 DC42 策略库中相关的策略进行回复。\n\n## DC42 ETF 轮动策略概览\n\n您好！";
    const { thinking, text } = splitThinkingFromText(raw);
    expect(thinking).toContain("用户问的是");
    expect(text.startsWith("## DC42")).toBe(true);
  });

  test("strips unclosed redacted_thinking during streaming", () => {
    const open = "<thinking>";
    const { thinking, text } = splitThinkingFromText(`${open}still thinking`);
    expect(thinking).toBe("still thinking");
    expect(text).toBe("");
  });

  test("strips <think> blocks (DeepSeek/MiniMax reasoning models)", () => {
    const raw = "<think>让我先分析一下小市值筛选。</think>\n\n## 推荐策略\n\n- 因子A\n- 因子B";
    const { thinking, text } = splitThinkingFromText(raw);
    expect(thinking).toBe("让我先分析一下小市值筛选。");
    expect(text).toBe("## 推荐策略\n\n- 因子A\n- 因子B");
  });

  test("strips unclosed <think> mid-stream", () => {
    const raw = "<think>还在思考中";
    const { thinking, text } = splitThinkingFromText(raw);
    expect(thinking).toBe("还在思考中");
    expect(text).toBe("");
  });
});

describe("extractReasoningFromMessage", () => {
  test("extracts reasoning blocks from array content", () => {
    const message = {
      id: "1",
      type: "ai",
      content: [
        { type: "reasoning", reasoning: "step 1" },
        { type: "text", text: "Answer" },
      ],
    } as unknown as Message;
    expect(extractReasoningFromMessage(message)).toBe("step 1");
  });

  test("extracts reasoning from additional_kwargs.reasoning_content", () => {
    const message = {
      id: "1",
      type: "ai",
      content: "",
      additional_kwargs: { reasoning_content: "provider reasoning" },
    } as unknown as Message;
    expect(extractReasoningFromMessage(message)).toBe("provider reasoning");
  });

  test("getLastAiMessage includes tool-call assistant turns", () => {
    const messages = [
      { id: "a1", type: "ai", content: "visible answer" },
      {
        id: "a2",
        type: "ai",
        content: [{ type: "reasoning", reasoning: "delegating" }],
        tool_calls: [{ id: "tc1", name: "lint_code_tool", args: {} }],
      },
    ] as Message[];

    expect(getLastAiMessage(messages)?.id).toBe("a2");
    expect(getLastVisibleAiMessage(messages)?.id).toBe("a1");
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

describe("extractReasoningSegmentsFromMessages", () => {
  test("returns one segment per AI message carrying reasoning", () => {
    const messages = [
      { id: "h1", type: "human", content: "hi" },
      {
        id: "a1",
        type: "ai",
        content: "",
        additional_kwargs: { reasoning_content: "thinking about round 1" },
        tool_calls: [{ id: "tc1", name: "search", args: {} }],
      },
      {
        id: "a2",
        type: "ai",
        content: "",
        additional_kwargs: { reasoning_content: "thinking about round 2" },
      },
    ] as unknown as Message[];

    const segments = extractReasoningSegmentsFromMessages(messages);

    expect(segments).toHaveLength(2);
    expect(segments[0]).toEqual({
      id: "a1",
      text: "thinking about round 1",
      isStreaming: false,
    });
    expect(segments[1]).toEqual({
      id: "a2",
      text: "thinking about round 2",
      isStreaming: false,
    });
  });

  test("preserves source order across mixed groups", () => {
    const messages = [
      {
        id: "a1",
        type: "ai",
        content: "",
        additional_kwargs: { reasoning_content: "first" },
      },
      { id: "h1", type: "human", content: "..." },
      {
        id: "a2",
        type: "ai",
        content: "",
        additional_kwargs: { reasoning_content: "second" },
      },
    ] as unknown as Message[];

    const segments = extractReasoningSegmentsFromMessages(messages);
    expect(segments.map((s) => s.text)).toEqual(["first", "second"]);
  });

  test("skips AI messages without reasoning", () => {
    const messages = [
      {
        id: "a1",
        type: "ai",
        content: "hello",
      },
      {
        id: "a2",
        type: "ai",
        content: "",
        additional_kwargs: { reasoning_content: "" },
      },
    ] as unknown as Message[];

    expect(extractReasoningSegmentsFromMessages(messages)).toEqual([]);
  });

  test("synthesises id when AIMessage id is missing", () => {
    const messages = [
      {
        type: "ai",
        content: "",
        additional_kwargs: { reasoning_content: "first" },
      },
      {
        type: "ai",
        content: "",
        additional_kwargs: { reasoning_content: "second" },
      },
    ] as unknown as Message[];

    const segments = extractReasoningSegmentsFromMessages(messages);
    expect(segments.map((s) => s.id)).toEqual([
      "reasoning-segment-0",
      "reasoning-segment-1",
    ]);
  });

  test("returns empty array for empty input", () => {
    expect(extractReasoningSegmentsFromMessages([])).toEqual([]);
  });

  test("only emits one segment per AIMessage (does not dedupe ids)", () => {
    // Two AIMessages sharing an id both appear; the function does not collapse
    // them — the slice-1 contract is one-segment-per-AIMessage, regardless of
    // repeated identifiers.
    const messages = [
      {
        id: "shared",
        type: "ai",
        content: "",
        additional_kwargs: { reasoning_content: "A" },
      },
      {
        id: "shared",
        type: "ai",
        content: "",
        additional_kwargs: { reasoning_content: "B" },
      },
    ] as unknown as Message[];

    const segments = extractReasoningSegmentsFromMessages(messages);
    expect(segments).toHaveLength(2);
  });
});

describe("convertToCoTSteps", () => {
  test("emits reasoning and tool_call steps interleaved per AIMessage", () => {
    const messages = [
      { id: "h1", type: "human", content: "go" },
      {
        id: "a1",
        type: "ai",
        content: "",
        additional_kwargs: { reasoning_content: "round 1 thinking" },
        tool_calls: [{ id: "tc1", name: "search", args: {} }],
      },
      {
        id: "t1",
        type: "tool",
        tool_call_id: "tc1",
        content: "result",
      },
      {
        id: "a2",
        type: "ai",
        content: "",
        additional_kwargs: { reasoning_content: "round 2 thinking" },
      },
    ] as unknown as Message[];

    const steps = convertToCoTSteps(messages);

    expect(steps).toHaveLength(3);
    expect(steps[0]).toMatchObject({
      kind: "reasoning",
      id: "a1",
      text: "round 1 thinking",
      isStreaming: false,
    });
    expect(steps[1]).toMatchObject({
      kind: "tool_call",
      id: "tc1",
      name: "search",
      status: "done",
    });
    expect(steps[2]).toMatchObject({
      kind: "reasoning",
      id: "a2",
      text: "round 2 thinking",
    });
  });

  test("skips AIMessages with no reasoning and no tool calls", () => {
    const messages = [
      { id: "a1", type: "ai", content: "plain final" },
    ] as Message[];

    expect(convertToCoTSteps(messages)).toEqual([]);
  });

  test("leaves tool_call step as running when no tool message follows", () => {
    const messages = [
      {
        id: "a1",
        type: "ai",
        content: "",
        tool_calls: [{ id: "tc1", name: "search", args: {} }],
      },
    ] as Message[];

    const steps = convertToCoTSteps(messages);
    expect(steps[0]).toMatchObject({ kind: "tool_call", status: "running" });
  });

  test("groups multiple tool calls of one AIMessage together", () => {
    const messages = [
      {
        id: "a1",
        type: "ai",
        content: "",
        additional_kwargs: { reasoning_content: "r" },
        tool_calls: [
          { id: "tc1", name: "first", args: {} },
          { id: "tc2", name: "second", args: {} },
        ],
      },
    ] as unknown as Message[];

    const steps = convertToCoTSteps(messages);
    // 1 reasoning + 2 tool calls
    expect(steps).toHaveLength(3);
    expect(steps.map((s) => (s as { kind: string }).kind)).toEqual([
      "reasoning",
      "tool_call",
      "tool_call",
    ]);
    expect((steps[1] as { name: string }).name).toBe("first");
    expect((steps[2] as { name: string }).name).toBe("second");
  });

  test("does not match tool messages to non-existent tool calls", () => {
    const messages = [
      {
        id: "a1",
        type: "ai",
        content: "",
        tool_calls: [{ id: "tc1", name: "search", args: {} }],
      },
      { id: "t_orphan", type: "tool", tool_call_id: "tc-other", content: "x" },
    ] as unknown as Message[];

    const steps = convertToCoTSteps(messages);
    expect((steps[0] as { status: string }).status).toBe("running");
  });

  test("marks only the matching AIMessage's reasoning as streaming", () => {
    const messages = [
      {
        id: "a1",
        type: "ai",
        content: "",
        additional_kwargs: { reasoning_content: "first reasoning" },
      },
      {
        id: "a2",
        type: "ai",
        content: "",
        additional_kwargs: { reasoning_content: "second reasoning" },
      },
      {
        id: "a3",
        type: "ai",
        content: "",
        additional_kwargs: { reasoning_content: "third reasoning" },
      },
    ] as unknown as Message[];

    const steps = convertToCoTSteps(messages, {
      streamingAIMessageId: "a2",
    });

    expect(steps).toHaveLength(3);
    expect((steps[0] as { isStreaming: boolean }).isStreaming).toBe(false);
    expect((steps[1] as { isStreaming: boolean }).isStreaming).toBe(true);
    expect((steps[2] as { isStreaming: boolean }).isStreaming).toBe(false);
  });

  test("none of the steps is streaming when streamingAIMessageId is omitted", () => {
    const messages = [
      {
        id: "a1",
        type: "ai",
        content: "",
        additional_kwargs: { reasoning_content: "first reasoning" },
      },
    ] as unknown as Message[];

    const steps = convertToCoTSteps(messages);
    expect((steps[0] as { isStreaming: boolean }).isStreaming).toBe(false);
  });

  test("does not match when streamingAIMessageId is missing on AIMessage", () => {
    const messages = [
      {
        type: "ai",
        content: "",
        additional_kwargs: { reasoning_content: "orphan reasoning" },
      },
    ] as unknown as Message[];

    // Even if streamingAIMessageId is supplied, an AIMessage without an id
    // cannot be matched — protects the synthetic-id fallback path.
    const steps = convertToCoTSteps(messages, {
      streamingAIMessageId: "anything",
    });
    expect((steps[0] as { isStreaming: boolean }).isStreaming).toBe(false);
  });

  // ── Slice 5: inline «THINK» fallback through convertToCoTSteps ─────────────

  // Note: `` markers below are written via Unicode escapes to survive the
  // editing tool's encoding of the literal `` characters.
  const lt = "<";
  const gt = ">";
  const tag = (name: string) => `${lt}${name}${gt}`;

  test("surfaces single closed  block as reasoning text", () => {
    const messages = [
      {
        id: "a1",
        type: "ai",
        content: `${tag("think")}让我先看小市值筛选的几个维度：估值、动量、流动性。${tag("/think")}\n\n## 推荐策略\n\n策略说明`,
      },
    ] as unknown as Message[];

    const steps = convertToCoTSteps(messages);
    expect(steps).toHaveLength(1);
    expect((steps[0] as { kind: string }).kind).toBe("reasoning");
    expect((steps[0] as { text: string }).text).toContain("小市值筛选");
  });

  test("joins two consecutive  blocks into one reasoning step", () => {
    const messages = [
      {
        id: "a1",
        type: "ai",
        content: `${tag("think")}第一步先看估值。${tag("/think")}${tag("think")}第二步看动量。${tag("/think")}\n\n## 推荐策略\n\n策略说明`,
      },
    ] as unknown as Message[];

    const steps = convertToCoTSteps(messages);
    expect(steps).toHaveLength(1);
    expect((steps[0] as { kind: string }).kind).toBe("reasoning");
    expect((steps[0] as { text: string }).text).toContain("估值");
    expect((steps[0] as { text: string }).text).toContain("动量");
  });

  test("merges additional_kwargs.reasoning_content with inline  block", () => {
    // Provider splits SOME reasoning via additional_kwargs and ALSO emits a
    // inline block. Both should land in the same reasoning step.
    const messages = [
      {
        id: "a1",
        type: "ai",
        content: `${tag("think")}下面看策略的具体回测表现：先模拟再实盘。${tag("/think")}\n\n## 推荐策略\n\n策略说明`,
        additional_kwargs: { reasoning_content: "已计算的因子值如下" },
      },
    ] as unknown as Message[];

    const steps = convertToCoTSteps(messages);
    expect(steps).toHaveLength(1);
    expect((steps[0] as { text: string }).text).toContain("已计算的因子值");
    expect((steps[0] as { text: string }).text).toContain("策略的具体回测表现");
  });

  test("strips redacted_ContentPart variant when reasoning_split is unset", () => {
    const messages = [
      {
        id: "a1",
        type: "ai",
        content: `${tag("redacted_thinking")}我需要结合小市值与动量因子进行分析；先回看历史表现；再给出建议。${tag("/redacted_thinking")}\n\n## 策略\n\n文字说明`,
      },
    ] as unknown as Message[];

    const steps = convertToCoTSteps(messages);
    expect(steps).toHaveLength(1);
    expect((steps[0] as { kind: string }).kind).toBe("reasoning");
    expect((steps[0] as { text: string }).text).toContain("小市值与动量");
  });

  test("does not surface a step when reasoning_text is empty after split", () => {
    // Content has tags but the inner text is whitespace-only. The pipeline
    // should skip rather than emit an empty reasoning step.
    const messages = [
      {
        id: "a1",
        type: "ai",
        content: `${tag("think")}   ${tag("/think")}\n\n## 推荐策略\n\n策略说明`,
      },
    ] as unknown as Message[];

    const steps = convertToCoTSteps(messages);
    expect(steps).toEqual([]);
  });
});

describe("splitThinkingFromText edge cases (slice 5)", () => {
  // Note: `` markers below are written via Unicode escapes (<>)
  // to survive the editor tool's encoding of the literal `` characters.
  const lt = "<";
  const gt = ">";
  const tag = (name: string) => `${lt}${name}${gt}`;

  test("matches uppercase THINK tags case-insensitively", () => {
    const raw = `${tag("THINK")}让我先分析。${tag("/THINK")}\n\n## 推荐策略\n\n策略说明`;
    const { thinking, text } = splitThinkingFromText(raw);
    expect(thinking).toBe("让我先分析。");
    expect(text).toBe("## 推荐策略\n\n策略说明");
  });

  test("matches redacted_thinking variants", () => {
    const raw =
      `${tag("redacted_thinking")}我需要计算小市值因子权重，然后再判断是否合适。${tag("/redacted_thinking")}\n\n## 推荐策略\n\n策略说明`;
    const { thinking, text } = splitThinkingFromText(raw);
    expect(thinking).toContain("小市值因子权重");
    expect(text).toContain("## 推荐策略");
  });

  test("processes multiple consecutive  blocks in one content string", () => {
    const raw =
      `${tag("think")}第一步：评估小市值估值水平。${tag("/think")}${tag("think")}第二步：评估动量表现。${tag("/think")}\n\n## 推荐策略\n\n策略说明`;
    const { thinking, text } = splitThinkingFromText(raw);
    expect(thinking).toContain("评估小市值估值水平");
    expect(thinking).toContain("评估动量表现");
    expect(text).toContain("## 推荐策略");
  });
});
