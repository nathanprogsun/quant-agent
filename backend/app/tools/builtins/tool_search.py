"""Tool search — deferred tool discovery at runtime.

Ports ``deerflow.tools.builtins.tool_search`` (lines 57-201). Provides:

- :class:`DeferredToolCatalog`: immutable, searchable catalog of deferred
  tools.
- :func:`build_tool_search_tool`: builds the ``tool_search`` tool as a
  closure over a catalog; it records promotions into graph state via
  :class:`langgraph.types.Command`.
- :func:`build_deferred_tool_setup`: assembles the catalog + tool from a
  policy-filtered tool list (call AFTER tool-policy filtering).
- :func:`assemble_deferred_tools`: builds the final tool list + deferred
  setup from a policy-filtered list (fail-closed).

A tool is "deferred" when it carries ``quant_agent_mcp`` metadata (see
:mod:`app.tools.mcp_metadata`). Deferred names are visible to the model
only in ``<available-deferred-tools>``; until :func:`tool_search` is
called, neither the schema nor the call is allowed.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass
from functools import cached_property
from typing import Annotated, Any

from langchain_core.messages import ToolMessage
from langchain_core.tools import BaseTool, InjectedToolCallId
from langchain_core.utils.function_calling import convert_to_openai_function
from langgraph.types import Command

from app.tools.mcp_metadata import is_mcp_tool

logger = logging.getLogger(__name__)

MAX_RESULTS = 5


def _compile_catalog_regex(pattern: str) -> re.Pattern[str]:
    """Case-insensitive regex; falls back to literal on invalid regex."""
    try:
        return re.compile(pattern, re.IGNORECASE)
    except re.error:
        return re.compile(re.escape(pattern), re.IGNORECASE)


def _catalog_regex_score(pattern: str, tool: BaseTool) -> int:
    regex = _compile_catalog_regex(pattern)
    return len(regex.findall(f"{tool.name} {tool.description or ''}"))


# ── Catalog ───────────────────────────────────────────────────────


@dataclass(frozen=True)
class DeferredToolCatalog:
    """Immutable catalog of deferred tools. Pure search, no mutation."""

    tools: tuple[BaseTool, ...]

    @cached_property
    def names(self) -> frozenset[str]:
        return frozenset(t.name for t in self.tools)

    @cached_property
    def hash(self) -> str:
        canon = [
            {"name": t.name, "schema": convert_to_openai_function(t)}
            for t in sorted(self.tools, key=lambda t: t.name)
        ]
        blob = json.dumps(canon, sort_keys=True, ensure_ascii=False, default=str)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]

    def search(self, query: str) -> list[BaseTool]:
        """Return up to :data:`MAX_RESULTS` tools matching ``query``.

        Query forms:
          - ``select:Read,Edit`` — fetch these exact tools by name.
          - ``+slack send``     — require ``slack`` in the name; rank
                                 the rest by description match.
          - any other string    — case-insensitive regex/substring match.
        """
        query = query.strip()
        if not query:
            return []

        if query.startswith("select:"):
            wanted = {n.strip() for n in query[7:].split(",")}
            return [t for t in self.tools if t.name in wanted][:MAX_RESULTS]

        if query.startswith("+"):
            parts = query[1:].split(None, 1)
            if not parts:
                return []
            required = parts[0].lower()
            candidates = [t for t in self.tools if required in t.name.lower()]
            if len(parts) > 1:
                candidates.sort(key=lambda t: _catalog_regex_score(parts[1], t), reverse=True)
            return candidates[:MAX_RESULTS]

        regex = _compile_catalog_regex(query)
        scored: list[tuple[int, BaseTool]] = []
        for t in self.tools:
            searchable = f"{t.name} {t.description or ''}"
            if regex.search(searchable):
                scored.append((2 if regex.search(t.name) else 1, t))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [t for _, t in scored][:MAX_RESULTS]


# ── Setup / tool ──────────────────────────────────────────────────


@dataclass(frozen=True)
class DeferredToolSetup:
    """Result of assembling deferred-tool support for one agent build.

    Three fields move as a unit; callers branch on ``tool_search_tool``:

    - **Empty** ``(None, frozenset(), None)`` — deferral is disabled, or
      no MCP tool survived policy filtering.
    - **Populated** — ``tool_search_tool`` appended to agent tools,
      ``deferred_names`` withheld from model until promoted,
      ``catalog_hash`` scopes promotions in graph state.

    Invariant: ``tool_search_tool is None`` ⟺ ``deferred_names`` empty ⟺
    ``catalog_hash is None``.
    """

    tool_search_tool: BaseTool | None
    deferred_names: frozenset[str]
    catalog_hash: str | None


def build_tool_search_tool(catalog: DeferredToolCatalog) -> BaseTool:
    """Build the ``tool_search`` tool, closing over ``catalog``."""
    from langchain_core.tools import StructuredTool
    from pydantic import BaseModel, Field

    catalog_hash = catalog.hash

    class _Args(BaseModel):
        """Injected by LangChain's ToolCall adapter — query is the user
        input; ``tool_call_id`` is filled from the dispatch ToolCall."""

        query: str = Field(description="Search query for the deferred catalog.")
        tool_call_id: Annotated[str, InjectedToolCallId]

    async def _coroutine(
        query: str,
        tool_call_id: Annotated[str, InjectedToolCallId],
    ) -> Command[Any]:
        """Fetch full schema definitions for deferred tools so they can be called.

        Deferred tools appear by name in ``<available-deferred-tools>`` in
        the system prompt. Until fetched, only the name is known. This
        tool matches a query against the deferred tools and returns the
        matched tools' complete schemas; once returned, a tool becomes
        callable.

        Query forms:
          - ``"select:Read,Edit"``        — fetch these exact tools by name.
          - ``"notebook jupyter"``        — keyword search, up to MAX_RESULTS.
          - ``"+slack send"``            — require ``slack`` in the name,
                                            rank the remaining terms.
        """
        matched = catalog.search(query)[:MAX_RESULTS]
        if not matched:
            content = f"No tools found matching: {query}"
            names: list[str] = []
        else:
            content = json.dumps(
                [convert_to_openai_function(t) for t in matched],
                indent=2,
                ensure_ascii=False,
            )
            names = [t.name for t in matched]
        return Command(
            update={
                "promoted": {"catalog_hash": catalog_hash, "names": names},
                "messages": [
                    ToolMessage(
                        content=content,
                        tool_call_id=tool_call_id,
                        name="tool_search",
                    )
                ],
            }
        )

    # InjectedToolCallId is a sentinel that LangChain resolves to the
    # current tool_call_id at invocation time; the mypy type for the
    # StructuredTool kwargs is ``dict[..., Any]`` so the kwarg flows
    # through cleanly. ``# noqa: E501`` keeps ruff quiet.
    return StructuredTool(
        name="tool_search",
        description=(
            "Fetch the full schema of one or more deferred tools so they can be "
            "called. Deferred tools are listed by name in <available-deferred-tools>."
        ),
        args_schema=_Args,
        coroutine=_coroutine,
    )


def build_deferred_tool_setup(
    filtered_tools: list[BaseTool],
    *,
    enabled: bool,
) -> DeferredToolSetup:
    """Build the deferred setup from a POLICY-FILTERED tool list.

    Must be called AFTER skill/agent tool-policy filtering so the catalog
    never exposes a tool the current agent is not allowed to use.

    Returns an empty setup when deferral is disabled, or it is enabled
    but no MCP tool survived filtering.
    """
    if not enabled:
        return DeferredToolSetup(None, frozenset(), None)
    deferred = [t for t in filtered_tools if is_mcp_tool(t)]
    if not deferred:
        return DeferredToolSetup(None, frozenset(), None)
    catalog = DeferredToolCatalog(tuple(deferred))
    return DeferredToolSetup(build_tool_search_tool(catalog), catalog.names, catalog.hash)


def assemble_deferred_tools(
    filtered_tools: list[BaseTool],
    *,
    enabled: bool,
) -> tuple[list[BaseTool], DeferredToolSetup]:
    """Build the final tool list + deferred setup from a policy-filtered list.

    Call AFTER tool-policy filtering. Fail-closed: if ``tool_search`` is
    enabled and MCP tools survived filtering but no deferred set was
    recovered, raises rather than silently binding their schemas to the
    model.
    """
    deferred_setup = build_deferred_tool_setup(filtered_tools, enabled=enabled)
    if enabled and not deferred_setup.deferred_names and any(
        is_mcp_tool(t) for t in filtered_tools
    ):
        raise RuntimeError(
            "tool_search enabled and MCP tools survived policy filtering, "
            "but no deferred set was recovered - refusing to bind MCP "
            "schemas (fail-closed)."
        )
    final_tools = list(filtered_tools)
    if deferred_setup.tool_search_tool:
        final_tools.append(deferred_setup.tool_search_tool)
    return final_tools, deferred_setup


def get_deferred_tools_prompt_section(
    *,
    deferred_names: frozenset[str] = frozenset(),
) -> str:
    """Generate ``<available-deferred-tools>`` from an explicit set."""
    if not deferred_names:
        return ""
    names = "\n".join(sorted(deferred_names))
    return f"<available-deferred-tools>\n{names}\n</available-deferred-tools>"


# Public factory aliases used by the agent build sites.
build_tool_search = build_tool_search_tool


__all__ = [
    "MAX_RESULTS",
    "DeferredToolCatalog",
    "DeferredToolSetup",
    "assemble_deferred_tools",
    "build_deferred_tool_setup",
    "build_tool_search",
    "get_deferred_tools_prompt_section",
]
