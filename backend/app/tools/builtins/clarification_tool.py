"""Clarification tool — ask the user for missing information.

Registered as a tool with ``return_direct=True`` so ``create_agent``
routes to END after the tool is called. The actual interception and
user-facing question rendering is handled by ``ClarificationMiddleware``.
"""

from __future__ import annotations

from typing import Literal

from langchain.tools import tool


@tool("ask_clarification", parse_docstring=True, return_direct=True)
def ask_clarification_tool(
    question: str,
    clarification_type: Literal[
        "missing_info",
        "ambiguous_requirement",
        "approach_choice",
        "risk_confirmation",
        "suggestion",
    ],
    context: str | None = None,
    options: list[str] | None = None,
) -> str:
    """Ask the user for clarification when you need more information to proceed.

    Use this tool when you encounter situations where you cannot proceed without user input:

    - **Missing information**: Required details not provided (e.g., file paths, URLs, specific requirements)
    - **Ambiguous requirements**: Multiple valid interpretations exist
    - **Approach choices**: Several valid approaches exist and you need user preference
    - **Risky operations**: Destructive actions that need explicit confirmation
    - **Suggestions**: You have a recommendation but want user approval before proceeding

    The execution will be interrupted and the question will be presented to the user.
    Wait for the user's response before continuing.

    Best practices:
    - Ask ONE clarification at a time for clarity
    - Be specific and clear in your question
    - Don't make assumptions when clarification is needed
    - For risky operations, ALWAYS ask for confirmation
    - After calling this tool, execution will be interrupted automatically

    Args:
        question: The clarification question to ask the user. Be specific.
        clarification_type: The type of clarification needed.
        context: Optional context explaining why clarification is needed.
        options: Optional list of choices for the user.
    """
    # Placeholder — actual logic is in ClarificationMiddleware.awrap_tool_call,
    # which intercepts this tool call and returns a Command(goto=END).
    return "Clarification request processed by middleware"
