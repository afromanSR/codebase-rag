# Supported Stacks

This page documents stack support based on the current implementation in:

- src/codebase_rag/indexer/detector.py
- src/codebase_rag/indexer/chunkers.py
- src/codebase_rag/indexer/extractors.py

## 1. Support Tiers

Support is grouped into three tiers:

- **Full**: Structure-aware chunking for the stack's primary code files, plus stack-specific structured extraction (for example routes and migrations).
- **Partial**: Structure-aware chunking is available for common file types in these stacks, but no stack-specific routes/migrations extractor is wired.
- **Fallback**: The stack may still be detected, but primary language files use generic sliding-window chunking.

Note: `env` and `docker` extraction run for all stacks when `.env.example` and compose files exist.

## 2. Support Matrix

| Stack | Language | Detection Markers | Chunker | Extractors | Tier |
| - | - | - | - | - | - |
| laravel | php | `composer.json` and `artisan` | `.php` -> `chunk_php` (class/method/function), plus extension-based chunkers for other files | `routes` (Laravel), `migrations` (Laravel), `env`, `docker` | Full |
| go-chi | go | `go.mod` and `internal/server/` directory | `.go` -> `chunk_go` (struct/function), plus extension-based chunkers for other files | `routes` (Go), `migrations` (SQL), `env`, `docker` | Full |
| go | go | `go.mod` | `.go` -> `chunk_go` (struct/function), plus extension-based chunkers for other files | `routes` (Go), `migrations` (SQL), `env`, `docker` | Full |
| php | php | `composer.json` (without `artisan`) | `.php` -> `chunk_php`, plus extension-based chunkers for other files | `env`, `docker` | Partial |
| vue | typescript | `package.json` and at least one `.vue` file anywhere in repo | `.vue` -> `chunk_vue`, `.ts/.tsx` -> `chunk_typescript`, plus extension-based chunkers for other files | `env`, `docker` | Partial |
| nextjs | typescript | `package.json` and `next.config.*` in repo root | `.ts/.tsx` -> `chunk_typescript`; `.js` falls back to generic chunking | `env`, `docker` | Partial |
| nuxt | typescript | `package.json` and `nuxt.config.*` in repo root | `.ts/.tsx` -> `chunk_typescript`; `.js` falls back to generic chunking | `env`, `docker` | Partial |
| node | javascript | `package.json` (when Vue/Next/Nuxt checks do not match) | No dedicated `.js` chunker; generic `chunk_fallback` for `.js`, extension-based chunkers for `.md/.yml/.yaml/.ts/.tsx/.vue/.php/.go` if present | `env`, `docker` | Fallback |
| rust | rust | `Cargo.toml` | No `.rs` chunker; generic `chunk_fallback` for Rust code | `env`, `docker` | Fallback |
| dotnet | csharp | any `*.csproj` or any `*.sln` found recursively | No `.cs` chunker; generic `chunk_fallback` for C# code | `env`, `docker` | Fallback |
| java | java | `pom.xml` in repo root or `build.gradle*` in repo root | No `.java` chunker; generic `chunk_fallback` for Java/Kotlin code | `env`, `docker` | Fallback |
| unknown | unknown | no known marker matched | Generic `chunk_fallback` for unsupported suffixes, plus extension-based chunkers for supported suffixes | `env`, `docker` | Fallback |

### Extension-to-Chunker Mapping (from `get_chunker`)

- `.php` -> `chunk_php`
- `.go` -> `chunk_go`
- `.ts`, `.tsx` -> `chunk_typescript`
- `.vue` -> `chunk_vue`
- `.md` -> `chunk_markdown`
- `.yaml`, `.yml` -> `chunk_yaml`
- all other suffixes -> `chunk_fallback`

## 3. Per-Stack Details

### Laravel (Full)

- Detection:
  - Requires `composer.json` and `artisan`.
- `key_paths` populated by detector:
  - `routes`, `migrations`, `models`, `controllers`, `env`, `docker`, `tests`.
  - Common path merge also re-applies `env` and `docker` when files exist.
- Chunking behavior:
  - PHP chunker splits by class/function boundaries.
  - Class chunks use `chunk_type` `class` when class block is within token limit.
  - Large classes split by methods with `chunk_type` `method`.
  - Standalone functions use `chunk_type` `function`.
  - Fallback path uses `chunk_type` `text`.
- Structured extraction:
  - `routes`: Laravel route parser (`Route::get/post/put/delete/patch`, `Route::resource`, middleware groups).
  - `migrations`: Laravel migration parser (`Schema::create`, `$table->...`).
  - `env`: `.env.example` parser.
  - `docker`: compose parser.

### Go-Chi (Full)

- Detection:
  - Requires `go.mod` and `internal/server/`.
- `key_paths` populated by detector:
  - `docker`, `tests`, and conditional `cmd`, `internal` when directories exist.
  - Common path merge adds `env`/`docker` if files exist.
- Chunking behavior:
  - Go chunker emits `chunk_type` `struct` for `type ... struct` and `function` for `func` blocks.
  - If no regex matches, file falls back to `text` chunks.
- Structured extraction:
  - `routes`: Go route parser (`Get/Post/Put/Delete/Patch/Route` and `HandleFunc`).
  - `migrations`: SQL migration parser (`CREATE TABLE ...`).
  - `env`, `docker` always attempted.

### Go (Full)

- Detection:
  - Requires `go.mod` (after Go-Chi check).
- `key_paths` populated by detector:
  - `docker`, `tests` plus common `env`/`docker` merge when present.
- Chunking behavior:
  - Same as Go-Chi (`struct`, `function`, or fallback `text`).
- Structured extraction:
  - Same as Go-Chi (`routes`, SQL `migrations`, `env`, `docker`).

### Generic PHP (Partial)

- Detection:
  - `composer.json` without the Laravel `artisan` marker.
- `key_paths` populated by detector:
  - `env`, `docker`, `tests` plus common merge.
- Chunking behavior:
  - Same PHP chunker behavior as Laravel projects (`class`, `method`, `function`, fallback `text`).
- Structured extraction:
  - No PHP-specific routes/migrations extractor in `extract_structured()`.
  - `env` and `docker` still extracted when available.

### Vue (Partial)

- Detection:
  - `package.json` and at least one `.vue` file anywhere under repo root.
- `key_paths` populated by detector:
  - `env`, `docker`, `tests` plus common merge.
- Chunking behavior:
  - Vue chunker first extracts `<template>`, `<script>`, `<style>` blocks.
  - Emits `chunk_type` values `template`, `script`, `style`.
  - Oversized blocks split with fallback line windows but keep block chunk_type.
  - `.ts/.tsx` files in the repo use TypeScript chunker (`function`, `class`, `const`).
- Structured extraction:
  - No Vue routes/migrations extractor in `extract_structured()`.
  - `env` and `docker` extraction still applies.

### Next.js (Partial)

- Detection:
  - `package.json` and `next.config.*` in repo root.
- `key_paths` populated by detector:
  - No stack-specific keys; common merge may add `env`/`docker`.
- Chunking behavior:
  - TypeScript files use export-based chunking (`function`, `class`, `const`).
  - JavaScript files have no dedicated chunker and use fallback `text` chunks.
- Structured extraction:
  - No Next-specific routes/migrations extractor.
  - `env` and `docker` extraction still applies.

### Nuxt (Partial)

- Detection:
  - `package.json` and `nuxt.config.*` in repo root.
- `key_paths` populated by detector:
  - No stack-specific keys; common merge may add `env`/`docker`.
- Chunking behavior:
  - Same file-type behavior as Next.js in current implementation.
- Structured extraction:
  - No Nuxt-specific routes/migrations extractor.
  - `env` and `docker` extraction still applies.

### Node.js (Fallback)

- Detection:
  - `package.json` after Vue/Next/Nuxt checks fail.
- `key_paths` populated by detector:
  - No stack-specific keys; common merge may add `env`/`docker`.
- Chunking behavior:
  - No `.js` chunker currently.
  - JavaScript source typically uses fallback `text` chunking.
  - Any supported suffix in the same repo (`.ts`, `.md`, `.yml`, etc.) still uses its dedicated chunker.
- Structured extraction:
  - Only `env` and `docker` from global extractor calls.

### Rust (Fallback)

- Detection:
  - `Cargo.toml`.
- `key_paths` populated by detector:
  - No stack-specific keys; common merge may add `env`/`docker`.
- Chunking behavior:
  - No `.rs` chunker currently, so code files use fallback `text` chunks.
- Structured extraction:
  - `env` and `docker` only.

### .NET (Fallback)

- Detection:
  - Any `*.csproj` or `*.sln` found recursively.
- `key_paths` populated by detector:
  - No stack-specific keys; common merge may add `env`/`docker`.
- Chunking behavior:
  - No `.cs` chunker currently, so code files use fallback `text` chunks.
- Structured extraction:
  - `env` and `docker` only.

### Java (Fallback)

- Detection:
  - `pom.xml` at repo root or any `build.gradle*` at repo root.
- `key_paths` populated by detector:
  - No stack-specific keys; common merge may add `env`/`docker`.
- Chunking behavior:
  - No `.java` chunker currently, so code files use fallback `text` chunks.
- Structured extraction:
  - `env` and `docker` only.

### Unknown (Fallback)

- Detection:
  - No known marker matched.
- `key_paths` populated by detector:
  - Only common merge keys (`env`, `docker`) when files exist.
- Chunking behavior:
  - Supported suffixes still route to dedicated chunkers.
  - Unsupported suffixes use fallback `text` chunks.
- Structured extraction:
  - `env` and `docker` only.

## 4. Detection Priority

`detect_stack()` checks in this exact order:

1. Laravel (`composer.json` + `artisan`)
2. Generic PHP (`composer.json`)
3. Go-Chi (`go.mod` + `internal/server`)
4. Generic Go (`go.mod`)
5. Vue (`package.json` + any `.vue`)
6. Next.js (`package.json` + `next.config.*`)
7. Nuxt (`package.json` + `nuxt.config.*`)
8. Node.js (`package.json`)
9. Rust (`Cargo.toml`)
10. .NET (`*.csproj` or `*.sln`)
11. Java (`pom.xml` or `build.gradle*`)
12. Unknown

This order is important because earlier checks are more specific and would otherwise be shadowed by generic markers.

## 5. Chunker Details

- PHP (`chunk_php`):
  - Splits class blocks and standalone functions.
  - Large classes split by method signatures.
  - Uses `chunk_type`: `class`, `method`, `function`, fallback `text`.
- Go (`chunk_go`):
  - Splits `type ... struct` and `func` blocks.
  - Uses `chunk_type`: `struct`, `function`, fallback `text`.
- TypeScript (`chunk_typescript`):
  - Splits on exported `function`, `class`, and `const` declarations.
  - Uses `chunk_type`: `function`, `class`, `const`.
- Vue (`chunk_vue`):
  - Splits by `<template>`, `<script>`, `<style>` blocks.
  - Uses `chunk_type`: `template`, `script`, `style`.
  - Oversized blocks use fallback windows while preserving block type.
- Markdown (`chunk_markdown`):
  - Splits sections by `#`, `##`, `###` headers using header-level boundaries.
  - Uses `chunk_type`: `section`.
- YAML (`chunk_yaml`):
  - Splits by top-level keys.
  - For docker-compose files, prefers per-service chunking under `services`.
  - Uses `chunk_type`: `config`.
- Fallback (`chunk_fallback`):
  - Sliding-window line-based chunking with token overlap.
  - Preserves line boundaries and emits `chunk_type`: `text`.

## 6. My Language Is Not Listed

If your language/framework is not listed:

- Files are still indexed as long as they match your configured include patterns.
- Unsupported file suffixes use fallback sliding-window chunking.
- Those chunks still get embeddings and are searchable.
- Expect lower precision compared to structure-aware chunkers.
- No symbol extraction (`symbol_name` is `None`) and no stack-specific structured extraction.

See [development.md](development.md) for adding new stack/language support, and [configuration.md](configuration.md) for include/exclude controls.

## 7. Requesting New Language Support

To request support for a new language/framework, open a GitHub Issue using the feature request template:

- <https://github.com/afromanSR/codebase-rag/issues/new?template=feature_request.yml>

Please include:

- Language and framework name.
- Marker files/folders that identify the stack.
- Typical project structure (where routes, models, migrations, configs live).
- A few representative code snippets for chunk boundary expectations.
- Any structured data you want extracted (routes, migrations, env, compose, etc.).

For implementation guidance, see [development.md](development.md). For tuning what gets indexed today, see [configuration.md](configuration.md).
