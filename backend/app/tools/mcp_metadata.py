"""Single source of truth for the MCP-tool metadata tag.

A tool is "MCP-sourced" when it carries the ``quant_agent_mcp`` metadata flag.
The tag is *written* where MCP tools are loaded (:mod:`app.mcp.tools`) and
*read* by deferred-tool assembly (:mod:`app.tools.builtins.tool_search`) and
the agent build site (:mod:`app.core.chat.agent.lead_agent`).

This is a leaf module by design: it depends only on ``BaseTool`` so any
module (including the tool loader) can import it without import-cycle risk.
"""
from __future__ import annotations

from langchain_core.tools import BaseTool

MCP_TOOL_METADATA_KEY = "quant_agent_mcp"


def tag_mcp_tool(tool: BaseTool) -> BaseTool:
    """Mark ``tool`` as MCP-sourced. Mutates ``tool.metadata`` in place."""
    merged = {**(tool.metadata or {}), MCP_TOOL_METADATA_KEY: True}
    tool.metadata = merged
    return tool


def is_mcp_tool(tool: BaseTool) -> bool:
    """True when ``tool`` carries the MCP-source tag."""
    return bool((getattr(tool, "metadata", None) or {}).get(MCP_TOOL_METADATA_KEY))
