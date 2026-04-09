"""Step 1 — MCP Docker test.

Spins up the GitHub MCP server via Docker, lists available tools,
calls pull_request_read on a real public PR, and prints the raw response.

Prerequisites:
  - Docker running
  - GITHUB_TOKEN set in .env (needs 'repo' scope, or fine-grained with read on public repos)

Usage:
  cd backend
  venv/bin/python test_mcp.py
"""

import asyncio
import json
import os
import sys

from dotenv import load_dotenv

load_dotenv()


async def main() -> None:
    from mcp import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        print("ERROR: GITHUB_TOKEN not set in .env — grab one from https://github.com/settings/tokens")
        sys.exit(1)

    print("Starting GitHub MCP server via Docker …")
    print("(First run will pull the image — this can take a minute)\n")

    server_params = StdioServerParameters(
        command="docker",
        args=[
            "run", "-i", "--rm",
            "-e", f"GITHUB_PERSONAL_ACCESS_TOKEN={token}",
            "ghcr.io/github/github-mcp-server",
        ],
    )

    async with stdio_client(server_params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            print("Connected to MCP server.\n")

            # ---- List tools + show schema for the ones we care about ----
            tools_result = await session.list_tools()
            tools_by_name = {t.name: t for t in tools_result.tools}
            print(f"=== {len(tools_by_name)} Available Tools ===")
            for name in sorted(tools_by_name):
                print(f"  • {name}")

            key_tools = ["pull_request_read", "get_file_contents", "search_code"]
            for name in key_tools:
                tool = tools_by_name.get(name)
                if tool:
                    print(f"\n--- {name} schema ---")
                    print(f"  Description: {tool.description}")
                    if tool.inputSchema:
                        props = tool.inputSchema.get("properties", {})
                        required = tool.inputSchema.get("required", [])
                        for pname, pinfo in props.items():
                            req = " (required)" if pname in required else ""
                            print(f"  {pname}: {pinfo.get('type', '?')}{req} — {pinfo.get('description', '')}")

            # ---- Fetch a real public PR ----
            owner, repo, pr_number = "fastapi", "fastapi", 1
            print(f"\n{'=' * 60}")
            print(f"Calling pull_request_read method=get ({owner}/{repo}#{pr_number})")
            print("=" * 60)
            result = await session.call_tool(
                "pull_request_read",
                {"owner": owner, "repo": repo, "pullNumber": pr_number, "method": "get"},
            )
            print("\nRaw response:")
            for block in result.content:
                text = getattr(block, "text", str(block))
                # Try to pretty-print if it's JSON
                try:
                    parsed = json.loads(text)
                    print(json.dumps(parsed, indent=2)[:3000])
                except (json.JSONDecodeError, TypeError):
                    print(text[:3000])
                if len(text) > 3000:
                    print(f"\n… (truncated, total {len(text)} chars)")

            # ---- Also grab the diff to prove that works ----
            print(f"\n{'=' * 60}")
            print(f"Calling pull_request_read method=get_diff ({owner}/{repo}#{pr_number})")
            print("=" * 60)
            diff_result = await session.call_tool(
                "pull_request_read",
                {"owner": owner, "repo": repo, "pullNumber": pr_number, "method": "get_diff"},
            )
            print("\nDiff (first 2000 chars):")
            for block in diff_result.content:
                text = getattr(block, "text", str(block))
                print(text[:2000])
                if len(text) > 2000:
                    print(f"\n… (truncated, total {len(text)} chars)")

    print("\nMCP Docker test passed.")


if __name__ == "__main__":
    asyncio.run(main())
