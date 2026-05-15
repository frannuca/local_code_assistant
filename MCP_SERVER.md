# MCP Server Integration

This project now includes a FastMCP server that provides tools for LLM access to filesystem, git, and code analysis operations.

## Overview

The MCP (Model Context Protocol) server exposes the following categories of tools:

### Filesystem Tools
- `read_file` - Read file contents with optional line range
- `list_files` - List files in a directory or scan entire repository
- `write_file` - Write content to a file
- `append_file` - Append content to a file
- `delete_file` - Delete a file
- `file_exists` - Check if a path exists

### Git Tools
- `git_diff` - Show uncommitted changes
- `git_status` - Show repository status
- `git_log` - Show recent commits
- `git_add` - Stage files for commit
- `git_commit` - Create a commit
- `git_show` - Show commit details

### Code Analysis Tools
- `scan_repo` - Scan repository and list all text files
- `read_multiple_files` - Read multiple files at once
- `search_files` - Search for files matching patterns
- `auto_select_files` - Intelligently select relevant files based on query
- `apply_patch` - Apply a unified diff patch

## Installation

### 1. Install FastMCP

```bash
pip install fastmcp
```

### 2. Development Setup (from repo root)

```bash
# Install the package in development mode
pip install -e .
```

## Running the MCP Server

### Using the Command-Line Entry Point

```bash
# Start MCP server for the current directory
lca-mcp

# Start MCP server for a specific repository
lca-mcp --repo /path/to/repo
```

The server runs in stdio mode and outputs diagnostic messages to stderr. When used with an MCP client, it communicates via stdin/stdout.

### Programmatic Usage

```python
from local_code_assistant.mcp_server import server, set_repo_root
from pathlib import Path
import asyncio

# Set the repository root
repo = Path("/path/to/repo")
set_repo_root(repo)

# Run the server
asyncio.run(server.run_async(debug=False))
```

## Integration with LLM Clients

The MCP server follows the Model Context Protocol specification and can be integrated with MCP-compatible clients. Common integration patterns:

### Claude Desktop

Add to your Claude Desktop configuration (`~/.claude_desktop_config.json`):

```json
{
  "tools": [
    {
      "name": "local-code-assistant",
      "command": "lca-mcp",
      "args": ["--repo", "/path/to/your/repo"],
      "env": {}
    }
  ]
}
```

### Custom MCP Client

```python
import subprocess
import json
import asyncio
from local_code_assistant.mcp_server import server, set_repo_root
from pathlib import Path

async def main():
    repo = Path(".")
    set_repo_root(repo)
    
    # Get available tools
    tools = await server.list_tools()
    for tool in tools:
        print(f"Tool: {tool.name}")
        print(f"  Description: {tool.description}")
        print(f"  Input: {tool.inputSchema}")
        print()
    
    # Call a tool
    result = await server.call_tool("scan_repo", {"max_files": 50})
    print(result)

asyncio.run(main())
```

## Tool Usage Examples

### Reading a File

```
Tool: read_file
Arguments:
{
  "path": "src/main.py",
  "offset": 10,
  "limit": 20
}
```

### Listing Repository Files

```
Tool: list_files
Arguments:
{
  "path": ".",
  "recursive": true,
  "max_files": 100
}
```

### Finding Relevant Files for a Query

```
Tool: auto_select_files
Arguments:
{
  "question": "Where is the authentication logic?",
  "max_files": 10
}
```

### Getting Git Diff

```
Tool: git_diff
Arguments:
{
  "file": null,
  "staged": false
}
```

### Reading Multiple Files

```
Tool: read_multiple_files
Arguments:
{
  "files": ["src/auth.py", "src/config.py"],
  "max_chars_per_file": 50000
}
```

### Applying a Patch

```
Tool: apply_patch
Arguments:
{
  "patch_content": "--- a/file.py\n+++ b/file.py\n...",
  "dry_run": true
}
```

## Security Considerations

- **Path Traversal Protection**: File operations are restricted to the specified repository root. Attempts to access files outside the repo are rejected.
- **Timeout**: Git commands have a 30-second timeout to prevent hanging.
- **Text File Only**: Repository scanning only includes text files by default (excludes binaries).
- **Exclude Lists**: Certain directories are automatically excluded (`.git`, `node_modules`, `__pycache__`, etc.)

## Repository Context

When using the MCP server, it operates on:
- **Repository Root**: Set via `set_repo_root()` or `--repo` argument
- **Default Excludes**: See `local_code_assistant/repo.py` for excluded directories
- **Text Extensions**: Only files with recognized text extensions are scanned

## Architecture

The MCP server is built using the FastMCP framework:

1. **mcp_server.py**: Main MCP server implementation with all tools
2. **mcp_server_standalone.py**: Command-line runner with stdio transport
3. **repo.py**: Existing repository utilities (scanning, reading, git operations)

## Troubleshooting

### Server Won't Start

- Ensure FastMCP is installed: `pip install fastmcp`
- Check that the repository path exists and is readable
- Look for error messages in stderr

### Tool Calls Failing

- Verify the tool name is correct (use `list_tools()` to see available tools)
- Check that required arguments are provided with correct types
- For git tools, ensure you're in a git repository

### Path Issues

- Use relative paths relative to the repository root
- Absolute paths are converted to repository-relative paths
- Forward slashes work on all platforms

## API Reference

See the tool definitions in `mcp_server.py` for complete input schemas and descriptions.

## Development

To extend the MCP server with new tools:

1. Define the tool in the `list_tools()` function with its schema
2. Add a handler in the `call_tool()` function
3. Implement the tool logic in a supporting function
4. Test with a local MCP client

Example:

```python
@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="my_tool",
            description="What my tool does",
            inputSchema={
                "type": "object",
                "properties": {
                    "arg": {"type": "string"},
                },
                "required": ["arg"],
            },
        ),
        # ... other tools
    ]

@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    if name == "my_tool":
        result = _my_tool_impl(arguments)
        return [TextContent(type="text", text=result)]

def _my_tool_impl(args: dict) -> str:
    # Implementation here
    return "result"
```

