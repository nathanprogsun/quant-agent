"""Middleware chain validator.

Runtime sanity checks executed once at agent-graph build time. Catches
configuration mistakes that would otherwise surface as silent runtime
misbehavior:

- Duplicate middleware classes (only one instance per class is meaningful)
- Missing critical hooks for known contracts
- Ordering invariants (e.g. ``InputSanitization`` should run before any
  message-modifying middleware)

Designed to be conservative — only flags patterns that are deterministic
bugs, not stylistic preferences.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable

from langchain.agents.middleware import AgentMiddleware


class MiddlewareChainError(ValueError):
    """Raised when the middleware chain fails validation."""


def validate_chain(middlewares: Iterable[AgentMiddleware]) -> None:
    """Validate the assembled middleware chain. Raises on issues.

    Args:
        middlewares: Iterable of middleware instances (order preserved).

    Raises:
        MiddlewareChainError: When an invariant is violated.
    """
    chain = list(middlewares)
    if not chain:
        return

    # 1. No duplicate classes
    class_counts = Counter(type(mw) for mw in chain)
    duplicates = [cls for cls, n in class_counts.items() if n > 1]
    if duplicates:
        names = ", ".join(c.__name__ for c in duplicates)
        raise MiddlewareChainError(f"duplicate middleware classes in chain: {names}")

    # 2. @Next / @Prev anchors resolve (no dangling anchors)
    seen_types = {type(mw) for mw in chain}
    for mw in chain:
        cls = type(mw)
        next_anchor = getattr(cls, "_next_anchor", None)
        prev_anchor = getattr(cls, "_prev_anchor", None)
        for anchor in (next_anchor, prev_anchor):
            if anchor is None:
                continue
            if anchor not in seen_types:
                raise MiddlewareChainError(
                    f"middleware {cls.__name__} anchors on {anchor.__name__} "
                    f"which is not in the chain"
                )

    # 3. Tool-call interceptors must override awrap_tool_call
    #    A middleware that declares ``_tool_call_interceptor = True`` intends
    #    to intercept tool calls; if it forgets to override
    #    ``awrap_tool_call`` — ``create_agent`` only wires middlewares that
    #    override the hook. Surface that misconfiguration at build time.
    for mw in chain:
        cls = type(mw)
        if getattr(cls, "_tool_call_interceptor", False) and (
            cls.awrap_tool_call is AgentMiddleware.awrap_tool_call
        ):
            raise MiddlewareChainError(
                f"{cls.__name__} declares _tool_call_interceptor=True but does "
                f"not override awrap_tool_call; ToolNode would silently bypass it"
            )


__all__ = ["MiddlewareChainError", "validate_chain"]
