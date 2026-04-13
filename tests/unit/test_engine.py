from __future__ import annotations

import random

import pytest

from codebase_rag.search.engine import SearchEngine, SearchResult
from codebase_rag.store.lance import VECTOR_DIM


def _random_vector(seed: float = 0.1) -> list[float]:
    """Generate a deterministic vector for testing."""
    rng = random.Random(seed)
    return [rng.random() for _ in range(VECTOR_DIM)]


def _make_chunk_dict(
    id: str,
    text: str,
    repo_name: str = "test-repo",
    file_path: str = "src/main.py",
    abs_file_path: str = "/workspace/test-repo/src/main.py",
    start_line: int = 1,
    end_line: int = 10,
    language: str = "python",
    chunk_type: str = "function",
    symbol_name: str | None = "main",
    file_mtime: float = 1000.0,
) -> dict:
    return {
        "id": id,
        "text": text,
        "repo_name": repo_name,
        "file_path": file_path,
        "abs_file_path": abs_file_path,
        "start_line": start_line,
        "end_line": end_line,
        "language": language,
        "chunk_type": chunk_type,
        "symbol_name": symbol_name,
        "file_mtime": file_mtime,
    }


@pytest.fixture
def engine_with_data(tmp_path, monkeypatch):
    """Create a SearchEngine with pre-populated data."""
    data_dir = tmp_path / "data"
    monkeypatch.setenv("CODEBASE_RAG_DATA_DIR", str(data_dir))

    engine = SearchEngine(workspace_path=tmp_path, embedding_model="nomic-embed-text")
    store = engine.store

    chunks = [
        _make_chunk_dict(
            "c1",
            "def authenticate(user, password):",
            repo_name="backend",
            language="python",
            symbol_name="authenticate",
        ),
        _make_chunk_dict(
            "c2",
            "func HandleLogin(w http.ResponseWriter)",
            repo_name="backend",
            language="go",
            symbol_name="HandleLogin",
            file_path="handlers/auth.go",
        ),
        _make_chunk_dict(
            "c3",
            "export function useAuth()",
            repo_name="frontend",
            language="typescript",
            symbol_name="useAuth",
            file_path="composables/useAuth.ts",
        ),
        _make_chunk_dict(
            "c4",
            "# Authentication\nThis document describes auth.",
            repo_name="docs",
            language="markdown",
            chunk_type="section",
            symbol_name="Authentication",
            file_path="docs/auth.md",
        ),
        _make_chunk_dict(
            "c5",
            "CREATE TABLE users (id INT)",
            repo_name="backend",
            language="python",
            symbol_name="create_users",
            file_path="migrations/001.py",
        ),
    ]
    vectors = [_random_vector(seed=i) for i in range(len(chunks))]
    store.upsert_chunks(chunks, vectors)

    store.save_structured("backend", "routes", [{"method": "POST", "path": "/login"}])
    store.save_structured(
        "backend",
        "env",
        [{"name": "DB_HOST", "default": "localhost", "comment": ""}],
    )

    store.save_summary(
        "backend",
        {
            "name": "backend",
            "stack": "python",
            "framework": "FastAPI",
            "chunk_count": 3,
        },
    )
    store.save_summary(
        "frontend",
        {"name": "frontend", "stack": "vue", "framework": "Vue 3", "chunk_count": 1},
    )

    return engine


def test_search_returns_results(engine_with_data) -> None:
    """search() returns SearchResult objects."""
    engine = engine_with_data
    engine._embed_query = lambda q: _random_vector(seed=0)

    results = engine.search("authentication")

    assert len(results) > 0
    assert all(isinstance(r, SearchResult) for r in results)


def test_search_respects_limit(engine_with_data) -> None:
    engine = engine_with_data
    engine._embed_query = lambda q: _random_vector(seed=0)

    results = engine.search("auth", limit=2)

    assert len(results) <= 2


def test_search_filters_by_repo(engine_with_data) -> None:
    engine = engine_with_data
    engine._embed_query = lambda q: _random_vector(seed=0)

    results = engine.search("auth", repos=["frontend"])

    assert all(r.repo_name == "frontend" for r in results)


def test_search_filters_by_filetype(engine_with_data) -> None:
    engine = engine_with_data
    engine._embed_query = lambda q: _random_vector(seed=0)

    results = engine.search("auth", filetypes=["go"])

    assert all(r.language == "go" for r in results)


def test_search_result_fields(engine_with_data) -> None:
    engine = engine_with_data
    engine._embed_query = lambda q: _random_vector(seed=0)

    results = engine.search("auth", limit=1)

    assert len(results) == 1
    r = results[0]
    assert isinstance(r.chunk_text, str) and len(r.chunk_text) > 0
    assert isinstance(r.score, float) and r.score > 0
    assert isinstance(r.start_line, int)
    assert isinstance(r.end_line, int)


def test_search_empty_store(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CODEBASE_RAG_DATA_DIR", str(tmp_path / "data"))
    engine = SearchEngine(workspace_path=tmp_path)
    engine._embed_query = lambda q: _random_vector(seed=0)

    results = engine.search("anything")

    assert results == []


def test_lookup_returns_structured_data(engine_with_data) -> None:
    engine = engine_with_data

    routes = engine.lookup("routes", "backend")

    assert isinstance(routes, list)
    assert len(routes) == 1
    assert routes[0]["method"] == "POST"


def test_lookup_returns_none_for_missing(engine_with_data) -> None:
    engine = engine_with_data

    result = engine.lookup("routes", "nonexistent-repo")

    assert result is None


def test_summary_single_repo(engine_with_data) -> None:
    engine = engine_with_data

    summary = engine.summary("backend")

    assert isinstance(summary, dict)
    assert summary["name"] == "backend"
    assert summary["stack"] == "python"


def test_summary_all_repos(engine_with_data) -> None:
    engine = engine_with_data

    summaries = engine.summary()

    assert isinstance(summaries, list)
    assert len(summaries) == 2


def test_summary_missing_repo(engine_with_data) -> None:
    engine = engine_with_data

    result = engine.summary("nonexistent")

    assert result is None
