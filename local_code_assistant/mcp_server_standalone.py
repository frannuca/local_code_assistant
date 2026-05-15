#!/usr/bin/env python

"""Standalone MCP server runner for local code assistant."""

from __future__ import annotations

import argparse

import asyncio

import sys

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

sys.path.insert(0, str(ROOT))

from local_code_assistant.mcp_server import server, set_repo_root

async def run_http_server(repo: Path) -> None:

    """Run the MCP server using HTTP transport."""

    set_repo_root(repo)

    await server.run_async(

        transport="http",

        host="127.0.0.1",

        port=8000,

    )

async def main() -> None:

    parser = argparse.ArgumentParser(description="MCP server for local code assistant")

    parser.add_argument(

        "--repo",

        default=".",

        help="Repository root to work with",

    )

    args = parser.parse_args()

    repo = Path(args.repo).resolve()

    if not repo.exists():

        print(f"Error: Repository not found: {repo}", file=sys.stderr)

        sys.exit(1)

    print(f"Starting MCP server for: {repo}", file=sys.stderr)

    print("Listening on http://127.0.0.1:8000/mcp/", file=sys.stderr)

    try:

        await run_http_server(repo)

    except KeyboardInterrupt:

        print("Server stopped", file=sys.stderr)

    except Exception as e:

        print(f"Error: {e}", file=sys.stderr)

        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())