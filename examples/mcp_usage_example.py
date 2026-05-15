#!/usr/bin/env python
"""Example: Using the MCP server programmatically."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from local_code_assistant.mcp_server import server, set_repo_root


async def main() -> None:
    """Demonstrate MCP server usage."""
    
    # Set the repository context
    repo = Path(".").resolve()
    print(f"Setting repository root to: {repo}\n")
    set_repo_root(repo)
    
    # List all available tools
    print("=" * 70)
    print("AVAILABLE TOOLS")
    print("=" * 70)
    tools = await server.list_tools()
    print(f"Found {len(tools)} tools:\n")
    for tool in tools:
        print(f"• {tool.name}")
        print(f"  {tool.description}")
    
    # Example 1: Scan the repository
    print("\n" + "=" * 70)
    print("EXAMPLE 1: Scan Repository")
    print("=" * 70)
    result = await server.call_tool("scan_repo", {"max_files": 10})
    print(result[0].text)
    
    # Example 2: List files in current directory
    print("\n" + "=" * 70)
    print("EXAMPLE 2: List Files in Root")
    print("=" * 70)
    result = await server.call_tool("list_files", {"path": ".", "recursive": False})
    print(result[0].text)
    
    # Example 3: Read a Python file
    print("\n" + "=" * 70)
    print("EXAMPLE 3: Read File (local_code_assistant/__init__.py)")
    print("=" * 70)
    result = await server.call_tool(
        "read_file",
        {"path": "local_code_assistant/__init__.py"}
    )
    print(result[0].text[:500])  # First 500 chars
    if len(result[0].text) > 500:
        print("...[truncated]")
    
    # Example 4: Git status
    print("\n" + "=" * 70)
    print("EXAMPLE 4: Git Status")
    print("=" * 70)
    result = await server.call_tool("git_status", {})
    status = result[0].text
    print(status if status else "(No changes - repository is clean)")
    
    # Example 5: Git log
    print("\n" + "=" * 70)
    print("EXAMPLE 5: Recent Git Commits")
    print("=" * 70)
    result = await server.call_tool("git_log", {"n": 5, "oneline": True})
    print(result[0].text)
    
    # Example 6: Auto-select files for a question
    print("\n" + "=" * 70)
    print("EXAMPLE 6: Auto-select Files for Query")
    print("=" * 70)
    result = await server.call_tool(
        "auto_select_files",
        {"question": "How does the CLI work?", "max_files": 5}
    )
    print(result[0].text)
    
    # Example 7: Search for files
    print("\n" + "=" * 70)
    print("EXAMPLE 7: Search for Python Files")
    print("=" * 70)
    result = await server.call_tool(
        "search_files",
        {"pattern": "*.py", "directory": "."}
    )
    files = result[0].text.split("\n")
    print(f"Found {len(files)} Python files:")
    for file in files[:10]:  # Show first 10
        if file:
            print(f"  {file}")
    if len(files) > 10:
        print(f"  ... and {len(files) - 10} more")
    
    # Example 8: Read multiple files
    print("\n" + "=" * 70)
    print("EXAMPLE 8: Read Multiple Files")
    print("=" * 70)
    files = [
        "local_code_assistant/__init__.py",
        "local_code_assistant/cli.py",
    ]
    result = await server.call_tool(
        "read_multiple_files",
        {"files": files, "max_chars_per_file": 200}
    )
    print(result[0].text[:800])  # First 800 chars
    if len(result[0].text) > 800:
        print("...[truncated]")
    
    # Example 9: Check if file exists
    print("\n" + "=" * 70)
    print("EXAMPLE 9: File Existence Check")
    print("=" * 70)
    result = await server.call_tool("file_exists", {"path": "pyproject.toml"})
    print(result[0].text)
    
    result = await server.call_tool("file_exists", {"path": "nonexistent_file.txt"})
    print(result[0].text)
    
    # Example 10: Write a test file
    print("\n" + "=" * 70)
    print("EXAMPLE 10: Write File (test)")
    print("=" * 70)
    test_content = "# This is a test file\nprint('Hello from MCP!')\n"
    result = await server.call_tool(
        "write_file",
        {"path": "test_mcp_example.txt", "content": test_content}
    )
    print(result[0].text)
    
    # Example 11: Append to file
    print("\n" + "=" * 70)
    print("EXAMPLE 11: Append to File")
    print("=" * 70)
    result = await server.call_tool(
        "append_file",
        {"path": "test_mcp_example.txt", "content": "\n# Added line\n"}
    )
    print(result[0].text)
    
    # Example 12: Read the test file
    print("\n" + "=" * 70)
    print("EXAMPLE 12: Read the Test File")
    print("=" * 70)
    result = await server.call_tool("read_file", {"path": "test_mcp_example.txt"})
    print(result[0].text)
    
    # Example 13: Delete the test file
    print("\n" + "=" * 70)
    print("EXAMPLE 13: Delete File")
    print("=" * 70)
    result = await server.call_tool("delete_file", {"path": "test_mcp_example.txt"})
    print(result[0].text)
    
    print("\n" + "=" * 70)
    print("Examples complete!")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())

