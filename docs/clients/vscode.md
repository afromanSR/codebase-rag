# VS Code / GitHub Copilot Setup

Use this guide to connect VS Code + GitHub Copilot Chat to `codebase-rag` over MCP.

## Prerequisites

- Python 3.11+
- Ollama installed and running:

```bash
brew install ollama && ollama serve
```

- `nomic-embed-text` model pulled:

```bash
ollama pull nomic-embed-text
```

- `uvx` available (comes with `uv`):

```bash
brew install uv
```

## Quick Setup (Recommended)

```bash
cd /path/to/your/workspace
uvx --from codebase-rag codebase-rag init
uvx --from codebase-rag codebase-rag index
```

This creates both `.copilot-rag.yaml` and `.vscode/mcp.json` automatically.

## Manual Setup

If you prefer manual configuration, create `.vscode/mcp.json` with:

```json
{
  "servers": {
    "codebase-rag": {
      "type": "stdio",
      "command": "uvx",
      "args": ["--from", "codebase-rag", "codebase-rag", "serve"],
      "env": {
        "CODEBASE_RAG_WORKSPACE": "${workspaceFolder}"
      }
    }
  }
}
```

## How It Works

- VS Code reads `.vscode/mcp.json` and spawns the MCP server via `uvx`.
- The server connects over stdio.
- `${workspaceFolder}` is a VS Code variable that resolves to the workspace root.
- Copilot Chat can then call `rag_search`, `rag_lookup`, `rag_summary`, and `rag_reindex`.

## Verification

1. Open the workspace in VS Code.
2. Open Copilot Chat.
3. Confirm the MCP server appears in the tools list.
4. Ask Copilot: "Use rag_summary to show me what repos are indexed"

## Re-indexing

- After pulling new code: `codebase-rag index` (incremental)
- After config changes: `codebase-rag index --full`

## Troubleshooting

See [../troubleshooting.md](../troubleshooting.md) for common issues.
