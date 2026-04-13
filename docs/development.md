# Development Guide

This guide explains how to extend codebase-rag with a new language or framework.

For full contributor setup, branch strategy, and PR process, see [CONTRIBUTING.md](../CONTRIBUTING.md).

See also:

- [supported-stacks.md](supported-stacks.md)
- [architecture.md](architecture.md)

## 1. Development Setup

Keep local setup minimal:

```bash
uv sync
```

Run tests:

```bash
# Unit tests
make test

# All tests (includes integration)
make test-all
```

Lint and format:

```bash
# Lint + format check
make lint

# Auto-fix + format
make format
```

## 2. Adding a New Language or Framework

In most cases, you will touch three files:

1. `src/codebase_rag/indexer/detector.py`
2. `src/codebase_rag/indexer/chunkers.py`
3. `src/codebase_rag/indexer/extractors.py` (optional)

### Step 1: Stack Detection (`detector.py`)

Add a new branch in `detect_stack()`.

Pattern used today:

- Check marker files/directories with `Path(...).is_file()` or `Path(...).is_dir()`.
- Populate `key_paths` for known locations (routes, migrations, tests, env, docker, etc.).
- Return via `_build_profile(...)`.

Current profile shape:

```python
@dataclass
class RepoProfile:
    name: str
    path: str
    stack: str
    language: str
    framework: str
    key_paths: dict[str, str] = field(default_factory=dict)
```

Example branch skeleton:

```python
if (root / "pyproject.toml").is_file() and (root / "src").is_dir():
    key_paths.update(
        {
            "tests": "tests",
            "env": ".env.example",
            "docker": "docker-compose.yml",
        }
    )
    return _build_profile(root, "python", "python", "Generic Python", key_paths)
```

Ordering rule: put more specific stacks before generic ones. The detector is an if-chain, so earlier matches win.

### Step 2: Language Chunker (`chunkers.py`)

Add a new chunker function and register it.

Current chunker function type:

```python
ChunkerFn = Callable[[Path, str, str, Path, int], list[Chunk]]
```

That corresponds to:

```python
def chunk_language(
    file_path: Path,
    content: str,
    repo_name: str,
    repo_path: Path,
    max_tokens: int,
) -> list[Chunk]:
    ...
```

Integration points:

1. Add suffix in `_LANGUAGE_BY_SUFFIX` so fallback chunks get the right `language`.
2. Add suffix-to-function mapping in `get_chunker()`.
3. Implement `chunk_<language>()` using the same metadata pattern as existing chunkers.

Chunking philosophy in this project:

- Prefer regex-based, structure-aware splits over AST dependencies.
- Split on meaningful boundaries (class/function/section/service blocks).
- Build chunks with `_make_chunk(...)` where possible.
- Populate metadata consistently: `chunk_type`, `symbol_name`, `start_line`, `end_line`.
- Fall back to `chunk_fallback(...)` when structure is unclear.

Minimal skeleton:

```python
def chunk_python(
    file_path: Path,
    content: str,
    repo_name: str,
    repo_path: Path,
    max_tokens: int,
) -> list[Chunk]:
    class_or_def = re.compile(r"^\s*(class|def)\s+([A-Za-z_][A-Za-z0-9_]*)", re.MULTILINE)
    matches = list(class_or_def.finditer(content))
    if not matches:
        return chunk_fallback(file_path, content, repo_name, repo_path, max_tokens)

    chunks: list[Chunk] = []
    for index, match in enumerate(matches):
        kind = match.group(1)
        name = match.group(2)
        start_offset = match.start()
        end_offset = matches[index + 1].start() if index + 1 < len(matches) else len(content)
        chunks.append(
            _make_chunk(
                file_path=file_path,
                repo_name=repo_name,
                repo_path=repo_path,
                content=content,
                start_offset=start_offset,
                end_offset=end_offset,
                chunk_type="class" if kind == "class" else "function",
                symbol_name=name,
                language="python",
            )
        )

    return chunks
```

### Step 3: Structured Extractors (`extractors.py`) (Optional)

Add structured extractors only when the stack has stable, high-value files (for example routes, migrations, env templates, compose files, dependency manifests).

Current pattern:

- Define dataclasses for extracted shapes (for example `RouteInfo`, `MigrationInfo`, `EnvVar`, `DockerService`).
- Write focused extraction functions (`extract_routes_*`, `extract_migrations_*`, etc.).
- Keep parsing resilient: return empty lists/objects on missing files or parse failures.
- Wire the stack into `extract_structured(repo_path, stack)` dispatch.

Current dispatch style:

```python
if stack == "laravel":
    routes = extract_routes_laravel(repo_path)
    migrations = extract_migrations_laravel(repo_path)
elif stack in {"go", "go-chi"}:
    routes = extract_routes_go(repo_path)
    migrations = extract_migrations_sql(repo_path)
```

If adding a new structured category, add a new dataclass and include the serialized payload in the returned dictionary.

## 3. Testing

Add tests beside existing suites:

- `tests/unit/test_detector.py`
- `tests/unit/test_chunkers.py`
- `tests/unit/test_extractors.py`

Follow current test style:

- Use `tmp_path` to create throwaway repos/files.
- Write realistic fixture text directly in the test.
- Call the concrete function under test.
- Assert observable behavior, not internals.

What to assert:

- Detector: `stack`, `language`, `framework`, and key paths.
- Chunkers: number of chunks, `chunk_type`, `symbol_name`, start/end line accuracy, fallback behavior.
- Extractors: parsed fields and empty results for missing files.

Typical examples from current tests:

- Detector tests create marker files with a helper and verify profile fields.
- Chunker tests verify boundaries (`class` vs `method`, export-based splits, markdown sections, YAML keys).
- Extractor tests verify parsed routes/migrations/env/docker and `extract_structured()` output keys.

Run:

```bash
make test
make lint
```

## 4. Concrete Walkthrough: Adding Python Support

This example shows the full extension flow.

1. Detect Python repos
   Add a detector branch for marker files such as `pyproject.toml`, `setup.py`, or `requirements.txt`.
   Return a `RepoProfile` such as:
   - `stack="python"`
   - `language="python"`
   - `framework="Generic Python"` (or a specific framework if detectable)

2. Add Python chunking
   In `chunkers.py`:
   - Add `".py": "python"` to `_LANGUAGE_BY_SUFFIX`.
   - Register `".py": chunk_python` in `get_chunker()` mapping.
   - Implement `chunk_python(...)` that splits on `class` and `def` boundaries and tags:
     - `chunk_type="class"` for classes
     - `chunk_type="function"` for functions
     - `symbol_name` with class/function name

3. Optional structured extraction
   If useful, add something like `extract_requirements(...)` to parse `requirements.txt` into a structured list of dependencies.
   Then wire it through `extract_structured(...)` for the new stack.

4. Add tests
   - Detector test for Python markers.
   - Chunker test for `.py` files with classes/functions.
   - Extractor test for `requirements.txt` parsing (if implemented).

5. Validate

```bash
make test
make lint
```

## 5. Code Conventions

Use project conventions consistently:

- Python 3.11+
- Type hints on public/internal function signatures
- Dataclasses for structured data
- `pathlib.Path` over `os.path`
- f-strings for formatting
- `logging` instead of `print` in library/server code (stderr-safe behavior)

For full conventions and contribution policy, see [CONTRIBUTING.md](../CONTRIBUTING.md).
