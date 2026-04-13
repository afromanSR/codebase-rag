# codebase-rag — Copilot Instructions

## Project Overview

**codebase-rag** is a local RAG-powered MCP (Model Context Protocol) server that indexes codebases and exposes semantic search to any MCP-compatible AI assistant (VS Code Copilot, Claude Desktop, Cline, Continue, Cursor, Windsurf, Zed, etc.).

**Problem it solves**: AI coding assistants re-read the same files every conversation, burning tokens. This tool indexes the entire workspace once, then serves precise, relevant code chunks on demand — reducing token usage by ~80-90%.

**Repository**: `afromanSR/codebase-rag`
**License**: MIT (open source)

---

## Architecture

- **Language**: Python 3.11+
- **Package manager**: uv (with uvx for execution)
- **MCP SDK**: `mcp` (FastMCP, stdio transport)
- **Vector store**: LanceDB (file-based, zero config, no server)
- **Embeddings**: Ollama with `nomic-embed-text` (local, no API keys)
- **CLI**: Click
- **Config**: YAML (`.copilot-rag.yaml` per workspace)
- **Testing**: pytest + pytest-asyncio

---

## Design Principles

1. **Tool is global, data is local**: Install once (`pipx install` or `uvx`), each workspace gets its own config + index.
2. **Zero external services**: Everything runs locally — Ollama for embeddings, LanceDB file-based storage. No API keys, no cloud.
3. **Generic, not project-specific**: Auto-detects repo stack (Laravel, Go, Vue, etc.) and applies appropriate chunking. Works on any codebase.
4. **MCP-native**: Built as an MCP server from day one. Any MCP client can connect. stdio transport (standard).
5. **Token-efficient**: Return just enough context (chunks + file location + surrounding lines) so the AI can act without re-reading entire files.

---

## Project Structure

```
codebase-rag/
├── pyproject.toml                          # uv project config, dependencies, CLI entrypoint
├── LICENSE                                 # MIT
├── README.md                               # Installation, quickstart, config reference
├── .github/
│   └── copilot-instructions.md             # THIS FILE
├── src/
│   └── codebase_rag/
│       ├── __init__.py                     # Package version
│       ├── cli.py                          # Click CLI: init, index, search, stats, serve
│       ├── config.py                       # YAML config loading + defaults (create when needed)
│       ├── server/
│       │   ├── __init__.py
│       │   └── mcp_server.py               # FastMCP server with 4 tools
│       ├── indexer/
│       │   ├── __init__.py
│       │   ├── core.py                     # Main indexing orchestrator
│       │   ├── chunkers.py                 # Language-aware chunking (PHP, Go, TS, MD, etc.)
│       │   ├── detector.py                 # Auto-detect repo stack from marker files
│       │   └── extractors.py               # Structured extractors (routes, migrations, env, docker)
│       ├── search/
│       │   ├── __init__.py
│       │   └── engine.py                   # Query interface over LanceDB
│       └── store/
│           ├── __init__.py
│           └── lance.py                    # LanceDB wrapper (create, upsert, search, delete, stats)
└── tests/
    ├── __init__.py
    ├── unit/
    │   ├── __init__.py
    │   ├── test_chunkers.py                # Test each language chunker
    │   ├── test_detector.py                # Test stack detection
    │   ├── test_extractors.py              # Test structured extraction
    │   ├── test_engine.py                  # Test search/ranking/filtering
    │   └── test_lance_store.py             # Test LanceDB CRUD
    └── integration/
        ├── __init__.py
        ├── test_indexer.py                 # Full index pipeline with mock embeddings
        └── test_mcp_server.py              # MCP tool registration and invocation
```

---

## Data Flow

```
Workspace files
    │
    ▼
[detector.py] → Identifies repo stack (Laravel, Go, Vue, etc.)
    │
    ▼
[chunkers.py] → Splits files into chunks (structure-aware by language)
[extractors.py] → Extracts structured data (routes, migrations, env)
    │
    ▼
[Ollama nomic-embed-text] → Generates embedding vectors
    │
    ▼
[lance.py] → Stores vectors + metadata in LanceDB
    │
    ▼
[engine.py] → Searches vectors, returns ranked results
    │
    ▼
[mcp_server.py] → Exposes search as MCP tools via stdio
    │
    ▼
AI Assistant (Copilot, Claude, etc.) calls tools
```

---

## Storage Layout

```
~/.local/share/codebase-rag/               # Global data directory (XDG-compliant)
└── indexes/
    └── {workspace_path_hash}/              # One index per workspace
        ├── vectors.lance/                  # LanceDB table files
        ├── metadata.json                   # Repos indexed, last index time, stats
        └── summaries/                      # Pre-computed repo summaries
            ├── {repo_name}.json            # Stack, models, endpoints, events
            └── ...

<any-workspace>/
├── .copilot-rag.yaml                       # Optional workspace config overrides
└── .vscode/
    └── mcp.json                            # MCP server registration
```

The workspace path hash ensures:
- Same repo in different workspaces shares index (keyed by absolute path)
- Different workspaces with different repos are isolated
- Easy to nuke: delete the hash directory

---

## Configuration (`.copilot-rag.yaml`)

Dropped into any workspace root. Auto-generated by `codebase-rag init`.

```yaml
version: 1
embedding_model: nomic-embed-text           # Must be pulled in Ollama

repos:
  auto_discover: true                       # Scan workspace for git repos
  # Or explicit:
  # paths:
  #   - ./my-backend
  #   - ./my-frontend

index:
  include:
    - "**/*.php"
    - "**/*.go"
    - "**/*.ts"
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
  max_tokens: 512
  overlap_tokens: 64
```

---

## MCP Server Specification

### Transport

stdio (standard MCP transport). Spawned by VS Code / Claude Desktop / any MCP client.

### VS Code `mcp.json` Config

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

### Tools (4 total)

#### `rag_search`

Semantic search across indexed repos. Primary token-saving tool.

**Parameters**:
- `query` (string, required): Natural language query or code snippet
- `repos` (list[string], optional): Filter to specific repo names
- `filetypes` (list[string], optional): Filter by file extension (e.g., ["php", "go"])
- `limit` (int, optional, default=10): Max results to return

**Returns**: Array of results, each with:
- `chunk_text`: The relevant code/doc chunk (~512 tokens max)
- `file_path`: Absolute file path
- `repo_name`: Repository name
- `start_line`: Starting line number (1-indexed)
- `end_line`: Ending line number
- `language`: Detected language
- `chunk_type`: "function", "class", "markdown_section", "config", etc.
- `score`: Relevance score (0-1)

#### `rag_lookup`

Structured data lookup for high-value files. No embedding search — direct retrieval.

**Parameters**:
- `category` (string, required): One of "routes", "migrations", "env", "docker", "models"
- `repo` (string, required): Repository name

**Returns**: Structured data (not chunks). For example:
- `routes`: All route definitions with method, path, controller, middleware
- `migrations`: All migration files with table name, columns, timestamps
- `env`: All .env.example variables with defaults
- `docker`: Services, ports, dependencies from docker-compose.yml

#### `rag_summary`

Pre-computed repo overview. Called at conversation start to avoid exploration.

**Parameters**:
- `repo` (string, optional): Specific repo name. If omitted, returns all repos.

**Returns**: Per repo:
- `name`: Repo name
- `stack`: Detected stack (e.g., "laravel", "go-chi", "vue3-typescript")
- `framework`: Framework name and version
- `key_files`: Important files and their purposes
- `models`: List of model/entity names
- `endpoints_count`: Number of API endpoints
- `last_indexed`: Timestamp of last index
- `chunk_count`: Number of indexed chunks

#### `rag_reindex`

Re-index specific repos or the entire workspace.

**Parameters**:
- `repos` (list[string], optional): Specific repos to re-index. Omit for full reindex.
- `full` (bool, optional, default=false): Force full reindex (ignore file mtimes)

**Returns**: Index statistics (repos indexed, chunks created, duration)

---

## Stack Detection (`detector.py`)

Auto-detect what stack a repo uses based on marker files:

| Marker File(s) | Stack | Language | Framework |
|----------------|-------|----------|-----------|
| `composer.json` + `artisan` | laravel | php | Laravel |
| `composer.json` (no artisan) | php | php | Generic PHP |
| `go.mod` | go | go | Generic Go |
| `go.mod` + `internal/server/` | go-chi | go | Chi (or detected from imports) |
| `package.json` + `*.vue` files | vue | typescript | Vue 3 |
| `package.json` + `next.config.*` | nextjs | typescript | Next.js |
| `package.json` + `nuxt.config.*` | nuxt | typescript | Nuxt |
| `package.json` (generic) | node | javascript/typescript | Node.js |
| `Cargo.toml` | rust | rust | Rust |
| `*.csproj` or `*.sln` | dotnet | csharp | .NET |
| `build.gradle*` or `pom.xml` | java | java | Java/Kotlin |

The detector returns a `RepoProfile` dataclass:

```python
@dataclass
class RepoProfile:
    name: str                    # Directory name
    path: str                    # Absolute path
    stack: str                   # e.g., "laravel", "go-chi", "vue"
    language: str                # Primary language
    framework: str               # Framework name
    key_paths: dict[str, str]    # Category → path mapping:
                                 #   "routes" → "routes/api.php"
                                 #   "migrations" → "database/migrations/"
                                 #   "models" → "app/Models/"
                                 #   "controllers" → "app/Http/Controllers/"
                                 #   "env" → ".env.example"
                                 #   "docker" → "docker-compose.yml"
                                 #   "tests" → "tests/"
```

---

## Chunking Strategy (`chunkers.py`)

Structure-aware, regex-based chunking. NO tree-sitter dependency — regex gives 90% of the benefit.

### PHP Chunker
- Split on `class ClassName` and `function methodName` boundaries
- Each class = 1 chunk (if < max_tokens), else split by methods
- Each standalone function = 1 chunk
- Capture: namespace, class name, method name, doc blocks

### Go Chunker
- Split on `func ` and `type ... struct` boundaries
- Each function = 1 chunk
- Each struct with methods = grouped
- Capture: package, function name, receiver type

### TypeScript/Vue Chunker
- `.vue` files: split `<script>`, `<template>`, `<style>` blocks, then split script by function/const
- `.ts` files: split by `export function`, `export class`, `export const`
- Capture: component name, exported symbols

### Markdown Chunker
- Split on `# `, `## `, `### ` headers
- Each section = 1 chunk (including nested content up to next same-level header)
- Capture: header hierarchy, section title

### YAML Chunker
- Split on top-level keys
- For `docker-compose.yml`: each service = 1 chunk
- Capture: top-level key name

### Fallback Chunker (all other files)
- Sliding window: max_tokens with overlap_tokens overlap
- Line-boundary aware (never split mid-line)
- Capture: line range only

### Chunk Dataclass

```python
@dataclass
class Chunk:
    id: str                      # f"{repo}:{file_path}:{start_line}"
    text: str                    # The chunk content
    repo_name: str               # Repository name
    file_path: str               # Path relative to repo root
    abs_file_path: str           # Absolute file path
    start_line: int              # 1-indexed
    end_line: int                # 1-indexed, inclusive
    language: str                # "php", "go", "typescript", "markdown", etc.
    chunk_type: str              # "class", "function", "method", "section", "config", "text"
    symbol_name: str | None      # Class/function/section name if detected
    file_mtime: float            # File modification time (for incremental indexing)
```

---

## Structured Extractors (`extractors.py`)

These extract structured (non-vector) data from well-known files. Stored as JSON alongside the vector index. Returned by `rag_lookup` tool.

### Route Extractor
- **Laravel** (`routes/api.php`): Parse `Route::get/post/put/delete/patch` calls. Extract method, URI, controller@action, middleware groups.
- **Go Chi** (`server.go` or router files): Parse `r.Get/Post/Put/Delete` calls. Extract method, pattern, handler function name.
- **Vue Router** (`router/index.ts`): Parse route definitions. Extract path, name, component, meta.

### Migration Extractor
- **Laravel** (`database/migrations/*.php`): Parse `Schema::create` calls. Extract table name, columns with types.
- **Go** (`migrations/*.sql` or `*.go`): Parse `CREATE TABLE` statements. Extract table name, columns.

### Env Extractor
- Parse `.env.example` files. Extract variable name, default value, inline comments.

### Docker Extractor
- Parse `docker-compose.yml`. Extract service names, images, ports, environment variables, depends_on.

---

## Indexing Pipeline (`core.py`)

### Full Index Flow

```python
def index_workspace(workspace_path: str, config: Config) -> IndexStats:
    # 1. Discover repos (auto-detect or from config)
    repos = discover_repos(workspace_path, config)

    # 2. For each repo:
    for repo_path in repos:
        # 2a. Detect stack
        profile = detect_stack(repo_path)

        # 2b. Walk files matching include/exclude patterns
        files = walk_files(repo_path, config.include, config.exclude)

        # 2c. Chunk each file with appropriate chunker
        chunks = []
        for file in files:
            chunker = get_chunker(file, profile)
            chunks.extend(chunker.chunk(file))

        # 2d. Extract structured data
        structured = extract_structured(repo_path, profile)

        # 2e. Generate embeddings via Ollama
        embeddings = embed_chunks(chunks, config.embedding_model)

        # 2f. Store in LanceDB
        store.upsert(chunks, embeddings)

        # 2g. Store structured data as JSON
        store.save_structured(repo_path, structured)

        # 2h. Generate and store repo summary
        store.save_summary(repo_path, profile, chunks, structured)
```

### Incremental Index Flow

- Compare file mtime against stored mtime in index metadata
- Only re-chunk and re-embed changed files
- Delete chunks for deleted files
- Structured extractors always re-run (they're fast)

### Embedding

```python
def embed_chunks(chunks: list[Chunk], model: str) -> list[list[float]]:
    """Generate embeddings via Ollama. Batch for efficiency."""
    client = ollama.Client()
    embeddings = []
    # Batch in groups of 100 for efficiency
    for batch in batched(chunks, 100):
        texts = [c.text for c in batch]
        response = client.embed(model=model, input=texts)
        embeddings.extend(response.embeddings)
    return embeddings
```

---

## Search Engine (`engine.py`)

### Semantic Search

```python
def search(
    query: str,
    repos: list[str] | None = None,
    filetypes: list[str] | None = None,
    limit: int = 10,
) -> list[SearchResult]:
    # 1. Embed the query
    query_embedding = embed_query(query)

    # 2. Search LanceDB with optional filters
    results = store.search(
        vector=query_embedding,
        filter_repos=repos,
        filter_languages=filetypes,
        limit=limit,
    )

    # 3. Return formatted results with context
    return [format_result(r) for r in results]
```

### SearchResult Dataclass

```python
@dataclass
class SearchResult:
    chunk_text: str
    file_path: str               # Absolute path
    repo_name: str
    start_line: int
    end_line: int
    language: str
    chunk_type: str
    symbol_name: str | None
    score: float                 # 0-1 relevance
```

### Lookup (Structured Data)

Direct JSON retrieval — no vector search. Returns pre-extracted routes, migrations, env, docker data.

### Summary

Returns pre-computed repo profile. Generated during indexing. Cheap to serve.

---

## CLI Specification (`cli.py`)

Built with Click. Entrypoint: `codebase-rag` (registered in pyproject.toml `[project.scripts]`).

### Commands

```bash
# Auto-discover repos and create .copilot-rag.yaml + .vscode/mcp.json
codebase-rag init

# Index the workspace (full or incremental)
codebase-rag index                          # Incremental (skip unchanged files)
codebase-rag index --full                   # Force full re-index
codebase-rag index --repo my-backend        # Index specific repo only

# Search from terminal (for testing)
codebase-rag search "authentication flow"
codebase-rag search "RabbitMQ events" --repo emis-be-applications --limit 5

# Show index statistics
codebase-rag stats

# Start MCP server (stdio mode — used by mcp.json config)
codebase-rag serve
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `CODEBASE_RAG_WORKSPACE` | Current working directory | Workspace root path |
| `CODEBASE_RAG_DATA_DIR` | `~/.local/share/codebase-rag` | Global data directory |
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama server URL |

---

## Implementation Plan (Phase by Phase)

### Phase 1: Core Infrastructure (No Dependencies Between Steps)

**Step 1.1 — `detector.py`** (Stack Auto-Detection)
- Implement `detect_stack(repo_path: str) -> RepoProfile`
- Check marker files in priority order
- Return RepoProfile with populated key_paths based on stack conventions
- **Tests** (`test_detector.py`):
  - Test Laravel detection (composer.json + artisan)
  - Test Go detection (go.mod)
  - Test Vue detection (package.json + .vue files)
  - Test unknown/generic repo
  - Test mixed stack (e.g., monorepo with multiple markers)
  - Test key_paths are correctly populated per stack

**Step 1.2 — `chunkers.py`** (Language-Aware Chunking)
- Implement base `Chunker` class with `chunk(file_path, content) -> list[Chunk]`
- Implement: `PhpChunker`, `GoChunker`, `TypeScriptChunker`, `VueChunker`, `MarkdownChunker`, `YamlChunker`, `FallbackChunker`
- Implement `get_chunker(file_path, profile) -> Chunker` factory function
- **Tests** (`test_chunkers.py`):
  - Test PHP: class with methods splits correctly, standalone functions
  - Test Go: func blocks, struct definitions
  - Test TS: export function, export class, export const
  - Test Vue: script/template/style block splitting
  - Test Markdown: header-based splitting at different levels
  - Test YAML: top-level key splitting, docker-compose service splitting
  - Test Fallback: sliding window respects line boundaries
  - Test Chunk metadata is correctly populated (id, line numbers, symbol_name)
  - Test max_tokens limit is respected

**Step 1.3 — `store/lance.py`** (LanceDB Wrapper)
- Implement `LanceStore` class with:
  - `__init__(workspace_path)` — compute hash, open/create LanceDB
  - `upsert_chunks(chunks, embeddings)` — insert or update chunks
  - `search(vector, filter_repos, filter_languages, limit)` — vector search with filters
  - `delete_repo(repo_name)` — remove all chunks for a repo
  - `get_stats()` — return chunk count, repo list, sizes
  - `save_structured(repo_name, data)` — store JSON structured data
  - `load_structured(repo_name, category)` — retrieve structured data
  - `save_summary(repo_name, summary)` — store repo summary
  - `load_summary(repo_name)` — retrieve repo summary
- **Tests** (`test_lance_store.py`):
  - Test create and upsert chunks with mock embeddings (random vectors)
  - Test search returns results sorted by relevance
  - Test repo filtering works
  - Test language filtering works
  - Test delete_repo removes all chunks
  - Test get_stats returns correct counts
  - Test structured data save/load roundtrip
  - Test summary save/load roundtrip
  - Use tmp_path fixture for isolated test directories

**Step 1.4 — `extractors.py`** (Structured Data Extraction)
- Implement `extract_routes(repo_path, profile) -> list[RouteInfo]`
- Implement `extract_migrations(repo_path, profile) -> list[MigrationInfo]`
- Implement `extract_env(repo_path) -> list[EnvVar]`
- Implement `extract_docker(repo_path) -> DockerComposeInfo`
- **Tests** (`test_extractors.py`):
  - Test Laravel route parsing (Route::get, Route::post, Route::resource, grouped)
  - Test Go route parsing (r.Get, r.Post patterns)
  - Test Laravel migration parsing (Schema::create, columns)
  - Test .env.example parsing (key=value, comments, empty values)
  - Test docker-compose.yml parsing (services, ports, depends_on)
  - Use fixture files with realistic content from real-world repos

### Phase 2: Indexing Pipeline

**Step 2.1 — `indexer/core.py`** (Main Orchestrator)
- Implement `discover_repos(workspace_path, config) -> list[str]`
- Implement `walk_files(repo_path, include, exclude) -> list[str]`
- Implement `index_workspace(workspace_path, config) -> IndexStats`
- Implement `index_repo(repo_path, config, store) -> RepoIndexStats`
- Implement incremental logic (mtime comparison, skip unchanged)
- **Tests** (`test_indexer.py` — integration):
  - Create a temp workspace with mock repos (a few .php, .go, .md files)
  - Mock Ollama embeddings (return random vectors of correct dimension)
  - Verify full index creates expected chunks in store
  - Verify incremental index skips unchanged files
  - Verify deleted files have chunks removed
  - Verify structured data is extracted and stored

### Phase 3: Search Engine

**Step 3.1 — `search/engine.py`** (Query Interface)
- Implement `SearchEngine` class using `LanceStore`
- Implement `search(query, repos, filetypes, limit) -> list[SearchResult]`
- Implement `lookup(category, repo) -> dict` (structured data retrieval)
- Implement `summary(repo) -> RepoSummary | list[RepoSummary]`
- **Tests** (`test_engine.py`):
  - Pre-populate a store with known chunks and mock embeddings
  - Test search returns results for a relevant query
  - Test repo filtering narrows results
  - Test filetype filtering works
  - Test limit parameter is respected
  - Test lookup returns structured data
  - Test summary returns repo profile

### Phase 4: MCP Server

**Step 4.1 — `server/mcp_server.py`** (FastMCP Server)
- Create FastMCP instance with 4 tools
- Each tool wraps the SearchEngine methods
- Reads `CODEBASE_RAG_WORKSPACE` from environment
- Logs to stderr (NEVER stdout — corrupts stdio transport)
- **Tests** (`test_mcp_server.py` — integration):
  - Test server creates successfully
  - Test all 4 tools are registered with correct schemas
  - Test rag_search returns valid results
  - Test rag_lookup returns structured data
  - Test rag_summary returns repo info
  - Test rag_reindex triggers re-indexing

### Phase 5: CLI

**Step 5.1 — `cli.py`** (Click CLI)
- Implement `init` command: discover repos, create `.copilot-rag.yaml`, create `.vscode/mcp.json`
- Implement `index` command: full/incremental indexing with progress output
- Implement `search` command: query and print results
- Implement `stats` command: display index info
- Implement `serve` command: start MCP server (stdio)
- Manual testing + smoke tests

### Phase 6: Polish

- README.md with installation, quickstart, config reference, contributing guide
- Initial git commit + push to GitHub
- Test with real EMIS workspace to validate token savings

---

## Code Conventions

### Python Style
- Python 3.11+ features: `match` statements, `StrEnum`, `dataclass`, `type` unions with `|`
- Type hints on all function signatures and return types
- Dataclasses for all data structures (not dicts)
- Use `pathlib.Path` over `os.path` everywhere
- f-strings for string formatting
- Async where needed (MCP server), sync everywhere else (indexing, CLI)
- No classes where a function suffices — avoid OOP for OOP's sake
- Use `logging` module with stderr handler (never print to stdout in server mode)

### Naming
- Modules: `snake_case.py`
- Classes: `PascalCase`
- Functions/methods: `snake_case`
- Constants: `UPPER_SNAKE_CASE`
- Dataclass fields: `snake_case`

### Error Handling
- Wrap errors with context: use specific exception classes where helpful
- Never silently swallow exceptions
- Log errors to stderr
- MCP tools should return error messages as strings, not raise exceptions (the AI can read the error and retry)

### Logging
- Use `logging.getLogger(__name__)` in each module
- Configure stderr handler (critical for stdio MCP transport)
- Levels: DEBUG for chunking details, INFO for indexing progress, WARNING for missing files, ERROR for failures

### Testing
- pytest with `pytest-asyncio` for async tests
- Use `tmp_path` fixture for all file/directory operations
- Mock Ollama embeddings in unit tests (return `[0.1] * 768` or random vectors)
- Mark integration tests with `@pytest.mark.integration`
- Integration tests can be skipped if Ollama is not running
- Test file fixtures in `tests/fixtures/` (sample PHP, Go, TS, MD files)
- Descriptive test names: `test_php_chunker_splits_class_by_methods`

### Imports
- Standard library first, then third-party, then local — separated by blank lines
- Prefer explicit imports over star imports
- Use `from __future__ import annotations` for forward references if needed

---

## Dependencies

### Runtime
| Package | Version | Purpose |
|---------|---------|---------|
| `mcp` | >=1.0 | MCP SDK — FastMCP server, stdio transport |
| `lancedb` | >=0.15 | File-based vector database |
| `ollama` | >=0.4 | Local embedding generation via Ollama |
| `click` | >=8.0 | CLI framework |
| `pyyaml` | >=6.0 | YAML config parsing |
| `pyarrow` | >=15.0 | LanceDB dependency for Arrow tables |

### Development
| Package | Version | Purpose |
|---------|---------|---------|
| `pytest` | >=8.0 | Test framework |
| `pytest-asyncio` | >=0.24 | Async test support |

### External
| Dependency | Purpose |
|------------|---------|
| Ollama | Local LLM/embedding server. Must be installed separately: `brew install ollama` |
| `nomic-embed-text` | Embedding model. Pull via: `ollama pull nomic-embed-text` |

---

## Development Commands

```bash
# Install dependencies
uv sync

# Run tests (unit only — no Ollama needed)
uv run pytest tests/unit/ -v

# Run all tests (needs Ollama running)
uv run pytest -v

# Run specific test
uv run pytest tests/unit/test_chunkers.py -v

# Run with coverage
uv run pytest --cov=codebase_rag -v

# Format (use ruff if added later, otherwise rely on uv fmt)
uv run ruff check --fix src/ tests/
uv run ruff format src/ tests/

# Build package
uv build

# Install locally for testing CLI
uv pip install -e .

# Test CLI
codebase-rag --help
codebase-rag init
codebase-rag index
codebase-rag search "some query"
codebase-rag stats
```

---

## MCP Server Critical Rules

1. **NEVER write to stdout** — stdout is the JSON-RPC transport. Use `logging` (stderr) or `print(..., file=sys.stderr)`.
2. **Tools return strings** — MCP tools return text content. Format results as readable text or JSON strings.
3. **Handle missing index gracefully** — If workspace is not indexed, return a helpful error message suggesting `codebase-rag index`.
4. **Handle missing Ollama gracefully** — If Ollama is not running, return an error message. Don't crash the server.
5. **Environment variable `CODEBASE_RAG_WORKSPACE`** — Set by MCP client config. This is how the server knows which workspace to search.

---

## User Preferences

- Concise code — no unnecessary abstractions
- Functions over classes unless state management is needed
- Tests for all mission-critical logic
- Type hints everywhere
- Descriptive variable and function names
- No over-engineering — build what's needed, nothing more
