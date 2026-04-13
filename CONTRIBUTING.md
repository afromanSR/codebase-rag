# Contributing to codebase-rag

Contributions are welcome! This guide will help you get started.

## Development Setup

```bash
git clone https://github.com/afromanSR/codebase-rag.git
cd codebase-rag
uv sync
```

## Running Tests

```bash
# Unit tests (no external dependencies)
make test

# All tests including integration (requires Ollama + nomic-embed-text)
make test-all
```

## Linting & Formatting

```bash
# Check for issues
make lint

# Auto-fix
make format
```

All code must pass `make lint` before merging.

## Commit Messages

We follow [Conventional Commits](https://www.conventionalcommits.org/):

- `feat:` — New feature
- `fix:` — Bug fix
- `docs:` — Documentation only
- `test:` — Adding or updating tests
- `chore:` — Maintenance (CI, deps, etc.)
- `refactor:` — Code change that neither fixes a bug nor adds a feature

Examples:
```
feat: add Ruby chunker
fix: handle empty files in Go chunker
docs: add Claude Desktop config example
```

## Pull Request Process

1. Fork the repository
2. Create a feature branch from `main`
3. Make your changes with tests
4. Ensure `make lint` and `make test` pass
5. Submit a pull request

## Code Style

- Python 3.11+ features (`match`, `StrEnum`, `X | Y` unions)
- Type hints on all function signatures
- `pathlib.Path` over `os.path`
- Dataclasses for data structures
- `logging` module (never `print` in library code)
- Functions over classes unless state management is needed

See [`.github/copilot-instructions.md`](.github/copilot-instructions.md) for full architecture and conventions.

## What's In Scope

- Language chunkers for additional languages
- Support for more MCP clients
- Performance improvements
- Better search relevance
- Additional structured extractors

## What's Out of Scope

- Cloud/hosted deployment
- Non-MCP integrations
- GUI/web interface
- Alternative embedding providers (keep it Ollama-only for simplicity)
