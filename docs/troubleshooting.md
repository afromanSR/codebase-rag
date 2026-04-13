# Troubleshooting

This guide maps common failures to concrete fixes using the current runtime behavior.

For setup details, see [configuration.md](configuration.md). For system internals, see [architecture.md](architecture.md).

## Ollama Issues

### Ollama Not Running

Problem

- Index or search fails when embedding requests cannot reach Ollama.

Symptoms

- `codebase-rag index` fails during embedding.
- `codebase-rag search` or MCP `rag_search` returns `Error: ...` with connection-related details.

Cause

- Ollama is not running on the configured host (default: `http://localhost:11434`).

Fix

1. Start Ollama:
   - `ollama serve`
   - or `brew services start ollama`
2. Verify Ollama is reachable:

```bash
curl http://localhost:11434/api/tags
```

If you use a non-default host, verify your `OLLAMA_HOST` environment variable.

### Embedding Model Not Pulled

Problem

- Embedding calls fail because the configured model is unavailable locally.

Symptoms

- Index/search/MCP tools return `Error: ...` mentioning model not found.

Cause

- `embedding_model` is set to a model that is not present in Ollama.

Fix

1. Pull the default model:

```bash
ollama pull nomic-embed-text
```

1. Ensure `.copilot-rag.yaml` uses the intended model under `embedding_model`.

## Search Issues

### Empty Search Results

Problem

- Search returns no matches.

Symptoms

- CLI: `No results found.`
- MCP `rag_search`: `No results found. Make sure the workspace is indexed (codebase-rag index).`

Cause

- Workspace has not been indexed.
- Query does not match indexed content.
- Wrong workspace path is being searched.

Fix

1. Check index status:

```bash
codebase-rag stats
```

1. If chunk count is 0 or repos are missing, run:

```bash
codebase-rag index
```

1. Confirm the workspace used by CLI/MCP is the one you expect.

### Stale or Outdated Results

Problem

- Results do not reflect current code.

Symptoms

- Recent edits do not appear in search output.

Cause

- Default indexing is incremental and uses file mtimes; in edge cases, unchanged mtimes can skip reprocessing.

Fix

1. Force a full reindex:

```bash
codebase-rag index --full
```

### Results From Wrong Repository

Problem

- Results come from repos you did not intend to include.

Symptoms

- Unexpected repo names appear in `search` output or `stats`.

Cause

- Auto-discovery included additional Git repositories in the workspace.

Fix

1. Configure explicit repos in `.copilot-rag.yaml`:
   - Set `repos.auto_discover: false`
   - Set `repos.paths` to only the repositories you want indexed
2. Reindex:

```bash
codebase-rag index --full
```

See [configuration.md](configuration.md) for examples.

## Configuration Issues

### Config File Errors

Problem

- Config is present but not applied.

Symptoms

- Startup/index proceeds with defaults unexpectedly.
- Warning in logs:
  - `Failed to parse config <path>: <yaml error> — using defaults`

Cause

- `.copilot-rag.yaml` has invalid YAML syntax.

Fix

1. Validate YAML syntax.
2. Correct the file and rerun your command.

Behavior note

- On YAML parse failure, config loading falls back to defaults rather than hard-failing.

### Files Not Being Indexed

Problem

- Expected files are absent from search.

Symptoms

- `codebase-rag stats` shows fewer chunks than expected.
- Searches for known symbols return no results.

Cause

- File path does not match `index.include` patterns.
- File path matches `index.exclude` patterns.
- File size exceeds hard limit (`MAX_FILE_SIZE_BYTES = 1048576`, 1 MiB).
- File stat/read edge cases can be skipped during file walking.

Fix

1. Review `.copilot-rag.yaml` include/exclude patterns.
2. Ensure target files are below 1 MiB when possible.
3. Reindex after config changes:

```bash
codebase-rag index --full
```

See [configuration.md](configuration.md) for pattern examples.

## MCP Server Issues

### Server Not Connecting

Problem

- MCP client cannot use the `codebase-rag` server.

Symptoms

- MCP tools fail to start or all calls return `Error: ...`.

Cause

- Invalid `.vscode/mcp.json` configuration.
- `uvx` is unavailable in PATH.
- Workspace env var not passed to server.

Fix

1. Verify `.vscode/mcp.json` has the expected server config.
2. Verify `uvx` is installed and runnable.
3. Ensure `CODEBASE_RAG_WORKSPACE` is set by the MCP client env block.

### CODEBASE_RAG_WORKSPACE not set

Problem

- MCP tool call fails before engine initialization.

Symptoms

- Error text:
  - `Error: CODEBASE_RAG_WORKSPACE environment variable is not set. Set it in your MCP client config (e.g., .vscode/mcp.json).`

Cause

- MCP client did not pass `CODEBASE_RAG_WORKSPACE`.

Fix

1. Add/fix env mapping in `.vscode/mcp.json`:
   - `"CODEBASE_RAG_WORKSPACE": "${workspaceFolder}"`
2. Restart MCP client/session.

### Workspace path does not exist

Problem

- MCP tool fails due to invalid workspace path.

Symptoms

- Error text:
  - `Error: Workspace path does not exist: <resolved_path>`

Cause

- `CODEBASE_RAG_WORKSPACE` points to a non-existent directory.

Fix

1. Verify the path is absolute and valid on the machine running the MCP server.
2. Update MCP config and restart the session.

## Data Issues

### Vector Dimension Mismatch

Problem

- Upsert fails while writing vectors to LanceDB.

Symptoms

- Error text like:
  - `embedding for chunk '<id>' has dimension <n> but expected 768`

Cause

- Stored schema expects 768-dimension vectors (`nomic-embed-text`), but embeddings were generated with a different dimension.

Fix

1. Keep `embedding_model` consistent.
2. Run a full reindex:

```bash
codebase-rag index --full
```

### Corrupt or Missing Index

Problem

- Search returns empty or inconsistent results despite indexing attempts.

Symptoms

- `stats` appears inconsistent with expected repos/chunks.
- Tool calls repeatedly return storage/search errors.

Cause

- Index files under the workspace hash are missing/corrupt.

Fix

1. Identify your active workspace path:

```bash
codebase-rag stats
```

1. Locate the index root:
   - Default base: `~/.local/share/codebase-rag/indexes/`
   - Or `CODEBASE_RAG_DATA_DIR/indexes/` if overridden
2. Remove the affected workspace hash directory.
3. Rebuild:

```bash
codebase-rag index --full
```

## Platform Notes

- macOS:
  - `~/.local/share/` may not already exist; it is created automatically on first store initialization.
- Linux:
  - Uses the same XDG-style default path: `~/.local/share/codebase-rag`.
