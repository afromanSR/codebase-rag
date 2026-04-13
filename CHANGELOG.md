# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.1.0] - 2026-04-13

### Added

- Repo stack auto-detection (Laravel, Go, Vue, Next.js, Nuxt, Rust, .NET, Java)
- Language-aware code chunking (PHP, Go, TypeScript, Vue, Markdown, YAML)
- Structured data extractors (routes, migrations, env vars, Docker services)
- LanceDB vector store with workspace-hashed storage
- Ollama embedding integration (nomic-embed-text)
- Incremental indexing with mtime-based skip
- Search engine with repo/filetype filtering
- FastMCP server with 4 tools (rag_search, rag_lookup, rag_summary, rag_reindex)
- Click CLI (init, index, search, stats, serve)
- YAML configuration (.copilot-rag.yaml)
- 96 unit and integration tests

[Unreleased]: https://github.com/afromanSR/codebase-rag/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/afromanSR/codebase-rag/releases/tag/v0.1.0
