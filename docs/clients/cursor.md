# Cursor Setup

Use this guide to connect Cursor to `codebase-rag` over MCP.

## Prerequisites

- Python 3.11+
- Ollama installed and running
- `nomic-embed-text` model pulled
- `uvx` available

## Setup

### 1. Index Your Workspace

```bash
cd /path/to/your/workspace
uvx --from codebase-rag codebase-rag init
uvx --from codebase-rag codebase-rag index
```

### 2. Configure Cursor

Cursor supports MCP servers via its settings. You can use either approach below.

#### **Option A: Project-level config** (recommended)

Create `.cursor/mcp.json` in your workspace root:

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

#### **Option B: Global config**

Add the same config via Cursor Settings -> MCP Servers.

Note: Unlike VS Code, Cursor may not support `${workspaceFolder}`. Use an absolute path for `CODEBASE_RAG_WORKSPACE`.

### 3. Verify

Open the workspace in Cursor, start a chat, and ask:

"Use rag_summary to show me what repos are indexed"

## Notes

- Cursor MCP support can vary between versions. Check [Cursor documentation](https://docs.cursor.com) for the latest config format.
- `codebase-rag` uses stdio transport, which is the standard MCP transport and is broadly supported.

## Troubleshooting

See [../troubleshooting.md](../troubleshooting.md) for common issues.
