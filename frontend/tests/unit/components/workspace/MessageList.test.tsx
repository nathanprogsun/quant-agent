// @vitest-environment jsdom
import type { Message } from "@langchain/langgraph-sdk";
import { render, screen } from "@testing-library/react";
import { describe, expect, test } from "vitest";

import { MessageList } from "@/components/workspace/MessageList";
import {
  extractReasoningFromMessage,
  getLastAiMessage,
} from "@/core/messages/utils";

describe("MessageList", () => {
  test("shows empty state when no messages", () => {
    render(<MessageList messages={[]} />);

    expect(screen.getByText("开始对话吧")).toBeInTheDocument();
  });

  test("shows loading state when isLoading and empty", () => {
    render(<MessageList messages={[]} isLoading />);

    expect(screen.getByText("思考..")).toBeInTheDocument();
    expect(screen.getByText("@StrategyBot")).toBeInTheDocument();
  });

  test("renders human message", () => {
    const messages = [
      { id: "h1", type: "human", content: "Hello" },
    ] as Message[];

    render(<MessageList messages={messages} />);

    expect(screen.getByText("Hello")).toBeInTheDocument();
  });

  test("renders AI message", () => {
    const messages = [
      { id: "a1", type: "ai", content: "Hi there" },
    ] as Message[];

    render(<MessageList messages={messages} />);

    expect(screen.getByText("Hi there")).toBeInTheDocument();
  });

  test("does not surface internal tool calls to the user", () => {
    const messages = [
      {
        id: "a1",
        type: "ai",
        content: "让我先搜索策略库",
        tool_calls: [{ id: "tc1", name: "search", args: { query: "test" } }],
      },
    ] as Message[];

    render(<MessageList messages={messages} />);

    expect(screen.queryByText("search")).not.toBeInTheDocument();
    expect(screen.queryByText("让我先搜索策略库")).not.toBeInTheDocument();
  });

  test("does not surface tool error payloads", () => {
    const messages = [
      {
        id: "t1",
        type: "tool",
        tool_call_id: "tc1",
        content: "Error: search is not a valid tool",
      },
    ] as Message[];

    render(<MessageList messages={messages} />);

    expect(screen.queryByText(/not a valid tool/)).not.toBeInTheDocument();
  });

  test("renders final assistant reply after tool round", () => {
    const messages = [
      {
        id: "a1",
        type: "ai",
        content: "让我先搜索策略库",
        tool_calls: [{ id: "tc1", name: "bash", args: { command: "ls" } }],
      },
      {
        id: "t1",
        type: "tool",
        tool_call_id: "tc1",
        content: "file1.txt\nfile2.txt",
      },
      { id: "a2", type: "ai", content: "Here are the files" },
    ] as Message[];

    render(<MessageList messages={messages} />);

    expect(screen.queryByText("bash")).not.toBeInTheDocument();
    expect(screen.queryByText(/file1\.txt/)).not.toBeInTheDocument();
    expect(screen.getByText("Here are the files")).toBeInTheDocument();
  });

  test("shows thinking indicator when loading with messages", () => {
    const messages = [
      { id: "h1", type: "human", content: "Hello" },
    ] as Message[];

    render(<MessageList messages={messages} isLoading />);

    expect(screen.getByText("思考..")).toBeInTheDocument();
  });

  test("shows streaming reasoning inside thinking block", () => {
    const messages = [
      { id: "h1", type: "human", content: "Hello" },
      {
        id: "a1",
        type: "ai",
        content: "",
        additional_kwargs: { reasoning_content: "分析小市值筛选条件" },
      },
    ] as unknown as Message[];

    const lastAi = getLastAiMessage(messages);
    expect(extractReasoningFromMessage(lastAi!)).toBe("分析小市值筛选条件");

    render(<MessageList messages={messages} isLoading />);

    expect(screen.getByTestId("thinking-reasoning-content")).toHaveTextContent(
      "分析小市值筛选条件",
    );
  });

  test("AI message shows BigQuant avatar", () => {
    const messages = [
      { id: "a1", type: "ai", content: "AI reply" },
    ] as Message[];

    render(<MessageList messages={messages} />);

    const avatar = screen.getByText("Q");
    expect(avatar).toBeInTheDocument();
    expect(avatar.parentElement).toHaveClass("rounded-full");
    expect(avatar.parentElement).toHaveClass("bg-red-500");
  });

  test("human message rendered as right-aligned bubble", () => {
    const messages = [
      { id: "h1", type: "human", content: "user question" },
    ] as Message[];

    render(<MessageList messages={messages} />);

    const bubble = screen.getByText("user question").closest("div");
    expect(bubble).toHaveClass("bg-gray-100");
  });
});
