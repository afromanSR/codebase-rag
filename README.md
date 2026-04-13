# codebase-rag

[![CI](https://github.com/afromanSR/codebase-rag/actions/workflows/ci.yml/badge.svg)](https://github.com/afromanSR/codebase-rag/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

Local RAG-powered MCP server that indexes codebases and serves precise code context to any MCP-compatible AI assistant.

Problem: AI coding assistants re-read the same files every conversation, burning tokens. codebase-rag indexes the entire workspace once, then serves relevant code chunks on demand — reducing token usage by ~80-90%.

Author: Samson Rwakabuguli

GitHub: https://github.com/afromanSR/codebase-rag

## How It Works

```text
Workspace files
  → Auto-detect stack (Laravel, Go, Vue, etc.)
  → Language-aware chunking (PHP, Go, TS, Markdown, YAML)
  → Embed via Ollama (nomic-embed-text, local)
  → Store in LanceDB (file-based, zero config)
  → Serve via MCP tools (stdio transport)
  → AI assistant queries on demand
```

## Features

- 4 MCP tools: `rag_search`, `rag_lookup`, `rag_summary`, `rag_reindex`
- Language-aware chunking for PHP, Go, TypeScript, Vue, Markdown, YAML
- Structured extraction: routes, migrations, env vars, Docker services
- Auto-detects repo stack: Laravel, Go, Vue, Next.js, Nuxt, Rust, .NET, Java
- Incremental indexing (only re-indexes changed files)
- Works with any MCP client: VS Code Copilot, Claude Desktop, Cline, Continue, Cursor, Windsurf, Zed

## Prerequisites

- Python 3.11+
- [Ollama](https://ollama.com) installed and running
- `ollama pull nomic-embed-text`

## Installation

```bash
# With uvx (recommended — no install needed)
uvx codebase-rag --help

# Or install globally
pipx install codebase-rag
# or
uv tool install codebase-rag
```

## Quickstart

```bash
cd /path/to/your/workspace

# 1. Initialize config
codebase-rag init

# 2. Index the workspace
codebase-rag index

# 3. Test with a search
codebase-rag search "authentication flow"

# 4. Start using with your MCP client (see below)
```

## MCP Client Configuration

**VS Code** — After running `codebase-rag init`, a `.vscode/mcp.json` is created automatically:

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

**Claude Desktop** — Add to `claude_desktop_config.json`:

```json
{
	"mcpServers": {
		"codebase-rag": {
			"command": "uvx",
			"args": ["--from", "codebase-rag", "codebase-rag", "serve"],
			"env": {
				"CODEBASE_RAG_WORKSPACE": "/absolute/path/to/workspace"
			}
		}
	}
}
```

## CLI Reference

| Command | Description |
|---------|-------------|
| `codebase-rag init` | Create `.copilot-rag.yaml` config and `.vscode/mcp.json` |
| `codebase-rag index` | Index workspace (incremental by default) |
| `codebase-rag index --full` | Force full re-index |
| `codebase-rag index --repo NAME` | Index a specific repo |
| `codebase-rag search QUERY` | Search from terminal |
| `codebase-rag search QUERY --repo NAME` | Search filtered to a repo |
| `codebase-rag stats` | Show index statistics |
| `codebase-rag serve` | Start MCP server (stdio) |

## MCP Tools

**`rag_search`** — Semantic search across indexed codebases. Returns code chunks with file locations, line numbers, and relevance scores.

**`rag_lookup`** — Direct retrieval of structured data: routes, migrations, env vars, Docker services. No embedding search.

**`rag_summary`** — Pre-computed repo overview: stack, framework, key files, endpoint count, chunk count.

**`rag_reindex`** — Trigger re-indexing from the AI assistant.

## Configuration (`.copilot-rag.yaml`)

```yaml
version: 1
embedding_model: nomic-embed-text

repos:
	auto_discover: true    # Scan for git repos in workspace

index:
	include:
		- "**/*.php"
		- "**/*.go"
		- "**/*.ts"
		- "**/*.vue"
		- "**/*.md"
		- "**/*.yaml"
		- "**/*.json"
	exclude:
		- "**/vendor/**"
		- "**/node_modules/**"
		- "**/.git/**"
		- "**/dist/**"

chunking:
	max_tokens: 512
	overlap_tokens: 64
```

## Supported Stacks

| Stack | Language | Detection |
|-------|----------|-----------|
| Laravel | PHP | `composer.json` + `artisan` |
| Generic PHP | PHP | `composer.json` |
| Go (Chi) | Go | `go.mod` + `internal/server/` |
| Generic Go | Go | `go.mod` |
| Vue 3 | TypeScript | `package.json` + `*.vue` files |
| Next.js | TypeScript | `package.json` + `next.config.*` |
| Nuxt | TypeScript | `package.json` + `nuxt.config.*` |
| Node.js | JavaScript | `package.json` |
| Rust | Rust | `Cargo.toml` |
| .NET | C# | `*.csproj` or `*.sln` |
| Java | Java | `pom.xml` or `build.gradle*` |

## Development

```bash
# Clone and install
git clone https://github.com/afromanSR/codebase-rag.git
cd codebase-rag
uv sync

# Run tests (unit only — no Ollama needed)
make test

# Run all tests (needs Ollama + nomic-embed-text)
make test-all

# Lint and format
make lint
make format
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for more details.

## License

MIT — see [LICENSE](LICENSE) for details.
