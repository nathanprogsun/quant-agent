// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test, vi } from "vitest";

import { InputBox } from "@/components/workspace/InputBox";

describe("InputBox", () => {
  test("renders textarea and send button", () => {
    render(<InputBox onSend={vi.fn()} />);

    expect(screen.getByPlaceholderText(/输入消息/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Send" })).toBeInTheDocument();
  });

  test("calls onSend with trimmed content on form submit", async () => {
    const onSend = vi.fn();
    render(<InputBox onSend={onSend} />);

    const textarea = screen.getByPlaceholderText(/输入消息/);
    await userEvent.type(textarea, "Hello world{Enter}");

    expect(onSend).toHaveBeenCalledWith("Hello world");
  });

  test("clears input after sending", async () => {
    const onSend = vi.fn();
    render(<InputBox onSend={onSend} />);

    const textarea = screen.getByPlaceholderText(/输入消息/) as HTMLTextAreaElement;
    await userEvent.type(textarea, "Hello{Enter}");

    expect(textarea.value).toBe("");
  });

  test("does not send empty or whitespace-only content", async () => {
    const onSend = vi.fn();
    render(<InputBox onSend={onSend} />);

    const textarea = screen.getByPlaceholderText(/输入消息/);
    await userEvent.type(textarea, "   {Enter}");

    expect(onSend).not.toHaveBeenCalled();
  });

  test("disables input and button when disabled prop is true", () => {
    render(<InputBox onSend={vi.fn()} disabled />);

    expect(screen.getByPlaceholderText(/输入消息/)).toBeDisabled();
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
  });

  test("Shift+Enter does not send message", async () => {
    const onSend = vi.fn();
    render(<InputBox onSend={onSend} />);

    const textarea = screen.getByPlaceholderText(/输入消息/);
    await userEvent.type(textarea, "Hello{Shift>}{Enter}");

    expect(onSend).not.toHaveBeenCalled();
  });

  test("send button click triggers send", async () => {
    const onSend = vi.fn();
    render(<InputBox onSend={onSend} />);

    const textarea = screen.getByPlaceholderText(/输入消息/);
    await userEvent.type(textarea, "Click test");

    await userEvent.click(screen.getByRole("button", { name: "Send" }));

    expect(onSend).toHaveBeenCalledWith("Click test");
  });
});
