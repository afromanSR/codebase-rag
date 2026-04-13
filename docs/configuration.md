# Configuration Reference

## 1. Overview

`codebase-rag` reads configuration from `.copilot-rag.yaml` in the workspace root.

- Generated automatically by `codebase-rag init`.
- If the config file is missing, defaults are used.
- If YAML parsing fails, defaults are used and a warning is logged.

The `init` command also creates or updates `.vscode/mcp.json` with a `codebase-rag` stdio server entry.

## 2. Full Annotated Example

```yaml
# Config schema version.
version: 1

# Embedding model passed to Ollama embed API.
embedding_model: nomic-embed-text

repos:
  # If true, discover git repos automatically:
  # - workspace root, if it contains .git/
  # - immediate child directories containing .git/
  auto_discover: true

  # Optional explicit repo list. Relative paths are resolved from workspace root.
  # Useful for monorepos or non-standard layouts.
  # paths:
  #   - ./services/api
  #   - ./apps/web

index:
  # Files are discovered recursively, then include/exclude patterns are applied.
  include:
    - "**/*.php"
    - "**/*.go"
    - "**/*.ts"
    - "**/*.tsx"
    - "**/*.vue"
    - "**/*.md"
    - "**/*.yaml"
    - "**/*.yml"
    - "**/*.json"
    - "**/routes/**"
    - "**/migrations/**"
    - "**/.env.example"
    - "**/docker-compose*.yml"

  exclude:
    - "**/vendor/**"
    - "**/node_modules/**"
    - "**/.rag/**"
    - "**/storage/**"
    - "**/dist/**"
    - "**/build/**"
    - "**/.git/**"
    - "**/docs/swagger*"
    - "**/public/docs/**"

chunking:
  # Target chunk size used by chunkers.
  max_tokens: 512

  # Token overlap between adjacent chunks (for sliding/fallback chunking).
  overlap_tokens: 64
```

## 3. Configuration Reference

### `version`

- Type: integer
- Default: `1`
- Description: Config schema version.

### `embedding_model`

- Type: string
- Default: `nomic-embed-text`
- Description: Ollama embedding model name used for indexing and query embedding.

### `repos.auto_discover`

- Type: boolean
- Default: `true`
- Description: Enables automatic git repo discovery in the workspace.
- Behavior:
  - Adds the workspace root if `.git/` exists.
  - Adds immediate child directories that contain `.git/`.
  - Deduplicates and sorts discovered paths.

### `repos.paths`

- Type: list of strings
- Default: empty list
- Description: Explicit repo paths to include.
- Notes:
  - Relative paths are resolved from workspace root.
  - Can be combined with auto discovery.
  - Only written to `.copilot-rag.yaml` by `save_config()` when non-empty.

### `index.include`

- Type: list of glob-style patterns
- Default:
  - `**/*.php`
  - `**/*.go`
  - `**/*.ts`
  - `**/*.tsx`
  - `**/*.vue`
  - `**/*.md`
  - `**/*.yaml`
  - `**/*.yml`
  - `**/*.json`
  - `**/routes/**`
  - `**/migrations/**`
  - `**/.env.example`
  - `**/docker-compose*.yml`
- Description: Files must match at least one include pattern when include is non-empty.

### `index.exclude`

- Type: list of glob-style patterns
- Default:
  - `**/vendor/**`
  - `**/node_modules/**`
  - `**/.rag/**`
  - `**/storage/**`
  - `**/dist/**`
  - `**/build/**`
  - `**/.git/**`
  - `**/docs/swagger*`
  - `**/public/docs/**`
- Description: Matching files are removed from indexing.

### `chunking.max_tokens`

- Type: integer
- Default: `512`
- Description: Maximum chunk size target used by chunkers.

### `chunking.overlap_tokens`

- Type: integer
- Default: `64`
- Description: Token overlap used when splitting content into adjacent chunks.

## 4. Environment Variables

| Variable | Default | Description |
| -------- | ------- | ----------- |
| `CODEBASE_RAG_WORKSPACE` | current working directory | Workspace root path. Used by CLI and server; MCP clients typically set this automatically. |
| `CODEBASE_RAG_DATA_DIR` | `~/.local/share/codebase-rag` | Global data directory for LanceDB indexes and metadata. |
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama server URL used by the Ollama client library. |

## 5. Include/Exclude Pattern Behavior

Pattern matching is implemented with Python `fnmatch` against repo-relative POSIX paths.

- File walk is recursive (`rglob("*")`).
- Include check runs first:
  - If include list is non-empty, a file must match at least one include pattern.
- Exclude check runs second:
  - If a file matches any exclude pattern, it is skipped.
- Special handling exists for patterns that begin with `**/`:
  - The matcher also tries the pattern without the `**/` prefix.
  - This allows patterns like `**/.env.example` to also match `.env.example` at repo root.
- Files larger than 1 MiB are skipped by the indexer.

## 6. Tips

- Add custom file types:
  - Extend `index.include`, for example `"**/*.py"`, `"**/*.sql"`, or `"**/*.proto"`.
- Exclude specific directories:
  - Add patterns like `"**/generated/**"` or `"**/coverage/**"` to `index.exclude`.
- Monorepo setup with explicit paths:
  - Keep `repos.auto_discover: true` for convenience and add `repos.paths` for non-git subprojects.
  - Or set `repos.auto_discover: false` and control all indexed repos through `repos.paths` only.

For config error handling, see [troubleshooting.md](troubleshooting.md).
For end-to-end flow, see [architecture.md](architecture.md).
