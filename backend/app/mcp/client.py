"""MCP client manager that spawns and communicates with the GitHub MCP server.

The GitHub MCP server (ghcr.io/github/github-mcp-server) runs as a Docker
container.  We communicate over stdio (stdin/stdout JSON-RPC) using the
official ``mcp`` Python SDK.  This module owns the full lifecycle: spawn the
container, initialize the MCP session, proxy tool calls, and tear down
cleanly.
"""

from __future__ import annotations

import logging
from contextlib import AsyncExitStack
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import CallToolResult, ListToolsResult, Tool

logger = logging.getLogger(__name__)

GITHUB_MCP_IMAGE = "ghcr.io/github/github-mcp-server"
DEFAULT_TOOLSETS = "repos,issues,pull_requests"


class MCPClientManager:
    """Manages the lifecycle of a GitHub MCP server connection.

    Usage::

        async with MCPClientManager() as client:
            await client.connect(github_token="ghp_...")
            tools = await client.list_tools()
            result = await client.call_tool("pull_request_read", {...})

    Or without the context manager::

        client = MCPClientManager()
        await client.connect(github_token="ghp_...")
        try:
            ...
        finally:
            await client.disconnect()
    """

    def __init__(self) -> None:
        self._session: ClientSession | None = None
        self._exit_stack: AsyncExitStack | None = None

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    async def __aenter__(self) -> MCPClientManager:
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:  # noqa: ANN001
        await self.disconnect()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(
        self,
        github_token: str,
        *,
        toolsets: str = DEFAULT_TOOLSETS,
    ) -> None:
        """Spawn the GitHub MCP server via Docker and open an MCP session.

        Parameters
        ----------
        github_token:
            A GitHub PAT (classic or fine-grained) with ``repo`` scope.
        toolsets:
            Comma-separated MCP toolsets to enable on the server.
        """
        if self._session is not None:
            logger.warning("Already connected — disconnecting first")
            await self.disconnect()

        server_params = StdioServerParameters(
            command="docker",
            args=[
                "run", "-i", "--rm",
                "-e", "GITHUB_PERSONAL_ACCESS_TOKEN",
                "-e", "GITHUB_TOOLSETS",
                GITHUB_MCP_IMAGE,
            ],
            env={
                "GITHUB_PERSONAL_ACCESS_TOKEN": github_token,
                "GITHUB_TOOLSETS": toolsets,
            },
        )

        # stdio_client and ClientSession are both async context managers.
        # We use AsyncExitStack to keep them open for the lifetime of this
        # manager rather than nesting two `async with` blocks.
        self._exit_stack = AsyncExitStack()

        try:
            read_stream, write_stream = await self._exit_stack.enter_async_context(
                stdio_client(server_params)
            )

            session = await self._exit_stack.enter_async_context(
                ClientSession(read_stream, write_stream)
            )

            init_result = await session.initialize()
            logger.info(
                "MCP session initialized — server: %s, version: %s",
                init_result.serverInfo.name,
                init_result.serverInfo.version,
            )

            self._session = session

        except Exception:
            logger.exception("Failed to connect to GitHub MCP server")
            await self._cleanup_exit_stack()
            raise

    async def disconnect(self) -> None:
        """Close the MCP session and stop the Docker container."""
        self._session = None
        await self._cleanup_exit_stack()
        logger.info("MCP client disconnected")

    # ------------------------------------------------------------------
    # Tool operations
    # ------------------------------------------------------------------

    async def list_tools(self) -> list[Tool]:
        """Return all tools exposed by the MCP server."""
        self._ensure_connected()
        assert self._session is not None

        result: ListToolsResult = await self._session.list_tools()
        logger.info("MCP server exposes %d tools", len(result.tools))
        return result.tools

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> CallToolResult:
        """Execute a tool on the MCP server and return the raw result.

        Raises
        ------
        RuntimeError
            If the MCP server returns ``isError=True``.
        """
        self._ensure_connected()
        assert self._session is not None

        logger.info("Calling MCP tool: %s(%s)", name, _truncate_args(arguments))

        try:
            result: CallToolResult = await self._session.call_tool(
                name, arguments=arguments
            )
        except Exception:
            logger.exception("MCP tool call failed: %s", name)
            raise

        if result.isError:
            error_text = _extract_text(result)
            logger.error("MCP tool %s returned error: %s", name, error_text)
            raise RuntimeError(f"MCP tool '{name}' error: {error_text}")

        logger.debug("MCP tool %s returned successfully", name)
        return result

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @property
    def is_connected(self) -> bool:
        return self._session is not None

    def _ensure_connected(self) -> None:
        if self._session is None:
            raise RuntimeError(
                "MCP client is not connected. Call connect() first."
            )

    async def _cleanup_exit_stack(self) -> None:
        if self._exit_stack is not None:
            try:
                await self._exit_stack.aclose()
            except Exception:
                logger.exception("Error during MCP exit stack cleanup")
            finally:
                self._exit_stack = None


def _extract_text(result: CallToolResult) -> str:
    """Pull plain text out of a CallToolResult's content list."""
    parts: list[str] = []
    for item in result.content:
        if hasattr(item, "text"):
            parts.append(item.text)
    return "\n".join(parts) if parts else "(no text content)"


def _truncate_args(args: dict[str, Any], max_len: int = 200) -> str:
    """Truncate argument dict repr for logging."""
    s = str(args)
    return s if len(s) <= max_len else s[:max_len] + "..."
