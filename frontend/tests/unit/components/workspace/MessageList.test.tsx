// @vitest-environment jsdom
import type { Message } from "@langchain/langgraph-sdk";
import { render, screen } from "@testing-library/react";
import { describe, expect, test } from "vitest";

import { MessageList } from "@/components/workspace/MessageList";

describe("MessageList", () => {
  test("shows empty state when no messages", () => {
    render(<MessageList messages={[]} />);

    expect(screen.getByText("开始对话吧")).toBeInTheDocument();
  });

  test("shows loading state when isLoading and empty", () => {
    render(<MessageList messages={[]} isLoading />);

    expect(screen.getByText("思考中...")).toBeInTheDocument();
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

  test("renders tool call indicators", () => {
    const messages = [
      {
        id: "a1",
        type: "ai",
        content: "",
        tool_calls: [{ id: "tc1", name: "search", args: { query: "test" } }],
      },
    ] as Message[];

    render(<MessageList messages={messages} />);

    expect(screen.getByText("search")).toBeInTheDocument();
  });

  test("renders tool message", () => {
    const messages = [
      {
        id: "t1",
        type: "tool",
        tool_call_id: "tc1",
        content: "search result data",
      },
    ] as Message[];

    render(<MessageList messages={messages} />);

    expect(screen.getByText("search result data")).toBeInTheDocument();
  });

  test("renders AI message with tool calls and tool results together", () => {
    const messages = [
      {
        id: "a1",
        type: "ai",
        content: "",
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

    expect(screen.getByText("bash")).toBeInTheDocument();
    expect(screen.getByText(/file1\.txt/)).toBeInTheDocument();
    expect(screen.getByText("Here are the files")).toBeInTheDocument();
  });

  test("shows thinking indicator when loading with messages", () => {
    const messages = [
      { id: "h1", type: "human", content: "Hello" },
    ] as Message[];

    render(<MessageList messages={messages} isLoading />);

    // Multiple "Thinking..." texts: one from empty state logic won't show, but the loading indicator will
    const thinkingElements = screen.getAllByText("思考中...");
    expect(thinkingElements.length).toBeGreaterThanOrEqual(1);
  });
});
