"""Bridge between MCP tool schemas and Gemini function declarations.

The GitHub MCP server exposes tools with JSON Schema ``inputSchema`` dicts.
Gemini's function-calling API accepts parameter schemas in the same JSON
Schema format, so the conversion is mostly a passthrough.  The main job here
is *filtering*: the GitHub MCP server exposes 40+ tools across every GitHub
API surface, but our agent only needs the subset relevant to PR review.
"""

from __future__ import annotations

import logging
from typing import Any

from mcp.types import Tool

logger = logging.getLogger(__name__)

# Substrings that a tool name must match (case-insensitive) to be included.
# Covers: pull_request_read, list_pull_requests, add_comment_to_pending_review,
# pull_request_review_write, get_file_contents, get_repository_tree,
# search_code, issue_write, issue_read, etc.
ALLOWED_TOOL_FRAGMENTS = (
    "pull_request",
    "get_file_contents",
    "get_repository_tree",
    "search_code",
    "add_comment",
    "issue",
)


def _is_relevant_tool(tool_name: str) -> bool:
    """Return True if the tool is needed for PR review."""
    name_lower = tool_name.lower()
    return any(fragment in name_lower for fragment in ALLOWED_TOOL_FRAGMENTS)


def mcp_tools_to_gemini_declarations(
    mcp_tools: list[Tool],
) -> list[dict[str, Any]]:
    """Convert MCP tool definitions to Gemini function declaration dicts.

    Each declaration has the shape::

        {
            "name": "pull_request_read",
            "description": "Get details for a single pull request",
            "parameters": { ... JSON Schema ... }
        }

    Gemini accepts JSON Schema for ``parameters`` directly, so the
    ``inputSchema`` from MCP is passed through with minimal cleanup.
    Only tools matching ``ALLOWED_TOOL_FRAGMENTS`` are included.
    """
    declarations: list[dict[str, Any]] = []

    for tool in mcp_tools:
        if not _is_relevant_tool(tool.name):
            continue

        parameters = tool.inputSchema
        # Ensure the schema has a top-level "type": "object" — Gemini
        # requires this even if the MCP server omits it.
        if "type" not in parameters:
            parameters = {**parameters, "type": "object"}

        declaration: dict[str, Any] = {
            "name": tool.name,
            "description": tool.description or f"MCP tool: {tool.name}",
            "parameters": parameters,
        }

        declarations.append(declaration)

    logger.info(
        "Converted %d/%d MCP tools to Gemini declarations: %s",
        len(declarations),
        len(mcp_tools),
        [d["name"] for d in declarations],
    )

    return declarations


def get_tool_names(mcp_tools: list[Tool]) -> list[str]:
    """Return a flat list of tool name strings — useful for logging."""
    return [tool.name for tool in mcp_tools]


def get_relevant_tool_names(mcp_tools: list[Tool]) -> list[str]:
    """Return only the tool names that pass the relevance filter."""
    return [tool.name for tool in mcp_tools if _is_relevant_tool(tool.name)]
