# MCP Tools Reference

This page documents the MCP tools exactly as implemented in the current codebase.

Related docs: [configuration.md](configuration.md) and [troubleshooting.md](troubleshooting.md).

## Overview

`codebase-rag` exposes 4 MCP tools over stdio transport via `FastMCP`:

- `rag_search`
- `rag_lookup`
- `rag_summary`
- `rag_reindex`

Any MCP-compatible client can call these tools.

## rag_search

Description (from code): **Semantic search across indexed codebases.**

### Parameters

| Name | Type | Required | Default | Notes |
| - | - | - | - | - |
| `query` | `str` | Yes | - | Natural language query or code snippet to search for. |
| `repos` | `list[str] \| None` | No | `None` | Repository-name filter passed through to search. |
| `filetypes` | `list[str] \| None` | No | `None` | Language/extension filter passed through as `filter_languages`. |
| `limit` | `int` | No | `10` | Maximum number of results returned by vector search. |

### Return Format

Returns a **single string**, not JSON.

If matches are found, output is markdown sections joined by blank lines:

````text
### Result {i} (score: {score:.3f})
**File**: {absolute_file_path} (lines {start_line}-{end_line})
**Repo**: {repo_name} | **Language**: {language} | **Type**: {chunk_type}[ | **Symbol**: {symbol_name}]
```{language}
{chunk_text}
```
````

No results:

```text
No results found. Make sure the workspace is indexed (codebase-rag index).
```

Errors (including missing workspace env var / Ollama failures):

```text
Error: {exception_message}
```

### Example Call (Natural Language)

"Search the indexed repos for where JWT authentication middleware is applied, show only Go files, top 5 results."

### Example Response

````markdown
### Result 1 (score: 0.913)
**File**: /Users/alex/work/api/internal/router/routes.go (lines 42-86)
**Repo**: api | **Language**: go | **Type**: function | **Symbol**: RegisterAuthRoutes
```go
func RegisterAuthRoutes(r chi.Router, h *Handler) {
    r.Group(func(r chi.Router) {
        r.Use(middleware.RequireJWT)
        r.Get("/me", h.GetProfile)
    })
}
```

### Result 2 (score: 0.889)
**File**: /Users/alex/work/api/internal/middleware/auth.go (lines 8-37)
**Repo**: api | **Language**: go | **Type**: function | **Symbol**: RequireJWT
```go
func RequireJWT(next http.Handler) http.Handler {
    return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
        // ...
    })
}
```
````

### Notes

- "Workspace not indexed" is not detected separately in `rag_search`; it uses the same no-results message.
- If the underlying table is missing/empty, search returns zero rows and produces the no-results message above.

## rag_lookup

Description (from code): **Look up structured data for a repository.**

### Parameters

| Name | Type | Required | Default | Notes |
| - | - | - | - | - |
| `category` | `str` | Yes | - | Category key used to load `structured/{repo}/{category}.json`. |
| `repo` | `str` | Yes | - | Repo name used as structured-data directory key. |

### Valid Categories (Actual Behavior)

`extract_structured(...)` currently writes only these categories:

- `routes`
- `migrations`
- `env`
- `docker`

Important discrepancy:

- The `rag_lookup` docstring mentions `models`, but `models` is not written by `extract_structured(...)`.
- A `models` lookup currently returns the standard "No ... data found" message unless some external process created that file.

### Return Format

Returns a **single string**:

- If data exists: pretty JSON (`json.dumps(data, indent=2)`)
- If missing: `No {category} data found for repo '{repo}'. Make sure it is indexed.`
- On error: `Error: {exception_message}`

### Category Payload Shapes

#### `routes`

JSON array of objects from `RouteInfo`:

| Field | Type | Notes |
| - | - | - |
| `method` | `str` | E.g. `GET`, `POST`, `RESOURCE`, `HANDLEFUNC`. |
| `path` | `str` | Route path/pattern. |
| `handler` | `str` | Raw handler expression/name from source. |
| `middleware` | `list[str]` | Present for all route objects (may be empty). |
| `name` | `str \| null` | Present, currently usually `null`. |

#### `migrations`

JSON array of objects from `MigrationInfo`:

| Field | Type | Notes |
| - | - | - |
| `file_name` | `str` | Migration filename. |
| `table_name` | `str` | Parsed table name. |
| `columns` | `list[str]` | Parsed columns (format depends on parser/source). |

#### `env`

JSON array of objects from `EnvVar`:

| Field | Type | Notes |
| - | - | - |
| `name` | `str` | Variable key. |
| `default` | `str` | Value part before inline comment. |
| `comment` | `str` | Inline comment after `#`, if present. |

#### `docker`

JSON object from `DockerComposeInfo`:

| Field | Type | Notes |
| - | - | - |
| `services` | `list[DockerService]` | List may be empty. |

Each `DockerService` object:

| Field | Type | Notes |
| - | - | - |
| `name` | `str` | Service name key from compose. |
| `image` | `str` | Image value or empty string. |
| `ports` | `list[str]` | Normalized as strings. |
| `environment` | `list[str]` | Dict entries become `KEY=value`. |
| `depends_on` | `list[str]` | List or dict keys normalized to strings. |

### Example Call (Natural Language)

"For repo `backend`, show me docker structured data."

### Example Response

```json
{
  "services": [
    {
      "name": "api",
      "image": "ghcr.io/example/api:latest",
      "ports": [
        "8080:8080"
      ],
      "environment": [
        "APP_ENV=local",
        "DB_HOST=db"
      ],
      "depends_on": [
        "db",
        "redis"
      ]
    }
  ]
}
```

## rag_summary

Description (from code): **Get pre-computed overview data for indexed repositories.**

### Parameters

| Name | Type | Required | Default | Notes |
| - | - | - | - | - |
| `repo` | `str \| None` | No | `None` | If set, loads one summary JSON; otherwise loads all summary JSON files. |

### Return Format

Returns a **single string**:

- If one repo requested and found: pretty JSON object
- If no repo specified: pretty JSON array of summary objects
- If missing:
  - repo provided: `No summary found for repo '{repo}'. Make sure the workspace is indexed (codebase-rag index).`
  - repo omitted: `No summaries found. Make sure the workspace is indexed (codebase-rag index).`
- On error: `Error: {exception_message}`

Summary object shape is created by indexing (`_build_summary(...)`) and persisted:

| Field | Type | Notes |
| - | - | - |
| `name` | `str` | Repo name. |
| `stack` | `str` | Detected stack id. |
| `framework` | `str` | Detected framework label. |
| `key_files` | `dict[str, str]` | Key paths from detector profile. |
| `models` | `list` | Currently defaults to empty list unless `structured["models"]` exists. |
| `endpoints_count` | `int` | Number of `routes` entries in structured data. |
| `chunk_count` | `int` | Repo chunk count from metadata (or fallback). |
| `last_indexed` | `str` | UTC timestamp format `%Y-%m-%dT%H:%M:%SZ`. |

### Example Response

```json
[
  {
    "name": "backend",
    "stack": "laravel",
    "framework": "Laravel",
    "key_files": {
      "routes": "routes/api.php",
      "migrations": "database/migrations",
      "models": "app/Models"
    },
    "models": [],
    "endpoints_count": 34,
    "chunk_count": 1260,
    "last_indexed": "2026-04-13T10:52:40Z"
  }
]
```

## rag_reindex

Description (from code): **Re-index specific repos or the entire workspace.**

### Parameters

| Name | Type | Required | Default | Notes |
| - | - | - | - | - |
| `repos` | `list[str] \| None` | No | `None` | If provided, disables auto-discovery and assigns these values to config `repo_paths`. |
| `full` | `bool` | No | `False` | If `true`, forces full reindex (ignores mtime skip logic). |

### Return Format

Returns a **single multiline string**:

```text
Indexed {repos_indexed} repo(s) in {duration_seconds:.1f}s
Files processed: {total_files}
Chunks created: {total_chunks}
  - {repo_name}: {files_processed} files, {chunks_created} chunks ({duration_seconds:.1f}s)
  - ...
```

On error:

```text
Error: {exception_message}
```

### Notes

- When `repos` is omitted, repository discovery follows config (`auto_discover` and `repos.paths`).
- When `repos` is provided, `auto_discover` is forced to `False`, and values are treated as `repo_paths` entries for discovery.
- `repo_paths` entries are resolved relative to workspace when not absolute paths.
- The docstring says "repository names", but behavior is effectively "repo path entries" accepted by config/discovery.
