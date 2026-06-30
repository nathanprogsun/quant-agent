// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

import { HomePromptInput } from "../HomePromptInput";
import { applySkillSuggestion, getMatchingSkillSuggestions } from "@/core/skills/suggestions";
import type { SkillDisclosure } from "@/core/skills/types";

// Stub useSkills so the component test does not hit the network.
vi.mock("@/core/skills", () => ({
  useSkills: () => ({
    skills: [
      { name: "deep-research", description: "Research a topic", category: "public", container_path: "/x", enabled: true },
      { name: "code-review", description: "Review code", category: "public", container_path: "/y", enabled: true },
      { name: "disabled-skill", description: "Off", category: "custom", container_path: "/z", enabled: false },
    ] as SkillDisclosure[],
    loading: false,
    error: null,
    reload: vi.fn(),
  }),
}));

describe("getMatchingSkillSuggestions", () => {
  const skills: SkillDisclosure[] = [
    { name: "deep-research", description: "d1", category: "public", container_path: "/a", enabled: true },
    { name: "code-review", description: "d2", category: "public", container_path: "/b", enabled: true },
    { name: "help", description: "reserved", category: "public", container_path: "/c", enabled: true },
    { name: "off", description: "off", category: "custom", container_path: "/d", enabled: false },
  ];

  it("returns enabled skills whose name starts with the prefix", () => {
    const out = getMatchingSkillSuggestions("deep", skills);
    expect(out.map((s) => s.name)).toEqual(["deep-research"]);
  });

  it("is case-insensitive", () => {
    const out = getMatchingSkillSuggestions("CODE", skills);
    expect(out.map((s) => s.name)).toEqual(["code-review"]);
  });

  it("excludes reserved names", () => {
    const out = getMatchingSkillSuggestions("help", skills);
    expect(out).toEqual([]);
  });

  it("excludes disabled skills", () => {
    const out = getMatchingSkillSuggestions("off", skills);
    expect(out).toEqual([]);
  });

  it("returns all enabled non-reserved skills for empty prefix (slash just typed)", () => {
    const out = getMatchingSkillSuggestions("", skills);
    expect(out.map((s) => s.name)).toEqual(["deep-research", "code-review"]);
  });

  it("caps results at 5 by default", () => {
    const many: SkillDisclosure[] = Array.from({ length: 10 }, (_, i) => ({
      name: `skill-${i}`,
      description: "d",
      category: "public",
      container_path: "/x",
      enabled: true,
    }));
    const out = getMatchingSkillSuggestions("skill-", many);
    expect(out.length).toBe(5);
  });
});

describe("applySkillSuggestion", () => {
  it("replaces the trailing slash token with /<name> ", () => {
    expect(applySkillSuggestion("hello /deep", "deep-research")).toBe("hello /deep-research ");
  });

  it("handles input that is just a slash command", () => {
    expect(applySkillSuggestion("/dep", "deep-research")).toBe("/deep-research ");
  });

  it("returns input unchanged when no slash present", () => {
    expect(applySkillSuggestion("no slash here", "x")).toBe("no slash here");
  });
});

describe("HomePromptInput slash autocomplete", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows suggestions when typing a slash prefix", () => {
    const onSend = vi.fn();
    render(<HomePromptInput onSend={onSend} />);
    const textarea = screen.getByRole("textbox") as HTMLTextAreaElement;
    fireEvent.change(textarea, { target: { value: "/deep" } });
    expect(screen.getByText("/deep-research")).toBeTruthy();
  });

  it("does not show suggestions for plain text", () => {
    const onSend = vi.fn();
    render(<HomePromptInput onSend={onSend} />);
    const textarea = screen.getByRole("textbox") as HTMLTextAreaElement;
    fireEvent.change(textarea, { target: { value: "hello world" } });
    expect(screen.queryByRole("listbox")).toBeNull();
  });

  it("Enter accepts the active suggestion and inserts /<name> ", () => {
    const onSend = vi.fn();
    render(<HomePromptInput onSend={onSend} />);
    const textarea = screen.getByRole("textbox") as HTMLTextAreaElement;
    fireEvent.change(textarea, { target: { value: "/code" } });
    expect(screen.getByText("/code-review")).toBeTruthy();
    fireEvent.keyDown(textarea, { key: "Enter" });
    expect((textarea as HTMLTextAreaElement).value).toBe("/code-review ");
    expect(onSend).not.toHaveBeenCalled();
  });

  it("ArrowDown then Enter selects the second suggestion", () => {
    const onSend = vi.fn();
    render(<HomePromptInput onSend={onSend} />);
    const textarea = screen.getByRole("textbox") as HTMLTextAreaElement;
    fireEvent.change(textarea, { target: { value: "/" } });
    fireEvent.keyDown(textarea, { key: "ArrowDown" });
    fireEvent.keyDown(textarea, { key: "Enter" });
    // Second suggestion is code-review (sorted order: code-review, deep-research)
    expect((textarea as HTMLTextAreaElement).value).toBe("/code-review ");
  });
});
