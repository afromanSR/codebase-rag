# Claude Desktop Setup

## Prerequisites

- Python 3.11+
- Ollama installed and running
- `nomic-embed-text` model pulled
- `uvx` available
- `codebase-rag` installed or accessible via `uvx`

## Setup

### 1. Index Your Workspace

```bash
cd /path/to/your/workspace
uvx --from codebase-rag codebase-rag init
uvx --from codebase-rag codebase-rag index
```

### 2. Configure Claude Desktop

Config file locations:

- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

Add this to the `mcpServers` section. `CODEBASE_RAG_WORKSPACE` must be an absolute path (do not use `${workspaceFolder}`, which is VS Code-specific):

```json
{
  "mcpServers": {
    "codebase-rag": {
      "command": "uvx",
      "args": ["--from", "codebase-rag", "codebase-rag", "serve"],
      "env": {
        "CODEBASE_RAG_WORKSPACE": "/absolute/path/to/your/workspace"
      }
    }
  }
}
```

### 3. Restart Claude Desktop

After editing the config, fully restart Claude Desktop.

### 4. Verify

Ask Claude: "Use rag_summary to show me what repos are indexed"

## Multiple Workspaces

To switch between workspaces, update the `CODEBASE_RAG_WORKSPACE` path and restart Claude Desktop. Each workspace has its own independent index.

## Troubleshooting

See [Troubleshooting](../troubleshooting.md).
