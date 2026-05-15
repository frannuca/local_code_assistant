# Examples

This directory contains example configurations and scripts for using the MCP server.

## Files

### `mcp_usage_example.py`
A comprehensive example showing how to use the MCP server programmatically. Demonstrates:
- Listing available tools
- Scanning the repository
- Reading files
- Git operations
- Auto-selecting files
- File operations (write, append, delete)

Run it with:
```bash
cd ..
python examples/mcp_usage_example.py
```

### `claude_config.example.json`
Example configuration for integrating the MCP server with Claude Desktop.

To use:
1. Copy or reference this configuration
2. Update the repo path to your repository
3. Add to `~/.claude_desktop_config.json`
4. Restart Claude Desktop

## Quick Start

### 1. Start the MCP Server

In one terminal, start the MCP server:
```bash
lca-mcp --repo /path/to/your/repo
```

### 2. Use with MCP Client

The server communicates via stdio with MCP clients like Claude Desktop, Cursor, or custom clients.

### 3. Example: Running the Usage Example

```bash
cd /Users/fran/code/ai/local_code_assistant
python examples/mcp_usage_example.py
```

## Integration with Different Clients

### Claude Desktop

1. Edit `~/.claude_desktop_config.json`
2. Add the MCP server configuration (see `claude_config.example.json`)
3. Restart Claude Desktop

### Cursor IDE

Similar to Claude Desktop, add the configuration to Cursor's MCP settings.

### Custom Python Client

```python
import asyncio
from local_code_assistant.mcp_server import server, set_repo_root
from pathlib import Path

async def main():
    set_repo_root(Path("/your/repo"))
    tools = await server.list_tools()
    for tool in tools:
        print(f"- {tool.name}: {tool.description}")

asyncio.run(main())
```

## Troubleshooting

### Import Errors

Make sure the package is installed:
```bash
pip install -e .
```

### FastMCP Not Found

Install FastMCP:
```bash
pip install fastmcp
```

### Permission Issues

Ensure the script is executable:
```bash
chmod +x mcp_usage_example.py
```

## Next Steps

- Read [MCP_SERVER.md](../MCP_SERVER.md) for detailed documentation
- Explore the available tools and their capabilities
- Integrate with your preferred LLM client

