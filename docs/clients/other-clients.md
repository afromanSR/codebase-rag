# Other MCP Clients

> Client-specific configuration formats change frequently. Always check each client's official documentation for the latest MCP setup instructions.

This guide focuses on the universal setup pattern that works across MCP clients.

## Generic Setup

codebase-rag works with **any MCP client** that supports stdio transport. The setup pattern is the same regardless of client:

1. **Index your workspace**: `cd /path/to/workspace && uvx --from codebase-rag codebase-rag init && uvx --from codebase-rag codebase-rag index`
2. **Configure the MCP server** in your client with:
   - Command: `uvx`
   - Arguments: `["--from", "codebase-rag", "codebase-rag", "serve"]`
   - Environment: `CODEBASE_RAG_WORKSPACE=/absolute/path/to/workspace`
3. **Restart the client** and verify with `rag_summary`

## Client-Specific Notes

### Cline (VS Code Extension)

- Configure via Cline's MCP settings panel
- Cline uses VS Code's MCP infrastructure - the `.vscode/mcp.json` config from `codebase-rag init` should work automatically
- See [Cline documentation](https://github.com/cline/cline) for MCP setup details

### Continue (VS Code / JetBrains)

- Configure in Continue's `config.json` under the `mcpServers` section
- See [Continue MCP docs](https://docs.continue.dev) for the exact config format

### Windsurf

- Configure via Windsurf's MCP settings
- Uses stdio transport, same command and args
- See [Windsurf documentation](https://docs.windsurf.com) for MCP server configuration

### Zed

- Zed supports MCP via its extensions system
- Configure in Zed's settings.json under MCP servers
- See [Zed documentation](https://zed.dev/docs) for MCP setup

## What All Clients Need

| Setting | Value |
| ------- | ----- |
| Transport | stdio |
| Command | `uvx` |
| Arguments | `--from codebase-rag codebase-rag serve` |
| Environment | `CODEBASE_RAG_WORKSPACE=/absolute/path/to/workspace` |

## Troubleshooting

See [../troubleshooting.md](../troubleshooting.md) for common issues.
