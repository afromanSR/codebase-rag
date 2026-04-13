from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from codebase_rag.config import Config
from codebase_rag.indexer.core import (
    discover_repos,
    index_repo,
    index_workspace,
    walk_files,
)
from codebase_rag.store.lance import LanceStore, VECTOR_DIM


def _make_fake_embeddings(count: int) -> list[list[float]]:
    """Return deterministic mock embeddings."""
    return [[0.1] * VECTOR_DIM for _ in range(count)]


@pytest.fixture(autouse=True)
def _isolated_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep LanceDB test data isolated per test run."""
    monkeypatch.setenv("CODEBASE_RAG_DATA_DIR", str(tmp_path / "data"))


@pytest.fixture
def workspace_with_repos(tmp_path: Path) -> Path:
    """Create a workspace with a mock git repo containing sample files."""
    repo = tmp_path / "my-backend"
    repo.mkdir()
    (repo / ".git").mkdir()

    php_dir = repo / "app" / "Http" / "Controllers"
    php_dir.mkdir(parents=True)
    (php_dir / "AuthController.php").write_text(
        "<?php\nnamespace App\\Http\\Controllers;\n\nclass AuthController {\n"
        "    public function login() {\n"
        "        return 'ok';\n"
        "    }\n"
        "}\n",
        encoding="utf-8",
    )

    (repo / "go.mod").write_text(
        "module example.com/backend\n\ngo 1.21\n", encoding="utf-8"
    )
    (repo / "main.go").write_text(
        'package main\n\nfunc main() {\n    println("hello")\n}\n',
        encoding="utf-8",
    )

    (repo / "README.md").write_text(
        "# My Backend\n\nA sample project.\n\n## Setup\n\nRun it.\n",
        encoding="utf-8",
    )

    (repo / ".env.example").write_text(
        "DB_HOST=localhost\nDB_PORT=5432\n", encoding="utf-8"
    )

    return tmp_path


def test_discover_repos_auto(workspace_with_repos: Path) -> None:
    config = Config(auto_discover=True)
    repos = discover_repos(workspace_with_repos, config)
    assert len(repos) == 1
    assert repos[0].name == "my-backend"


def test_discover_repos_explicit(workspace_with_repos: Path) -> None:
    config = Config(auto_discover=False, repo_paths=["./my-backend"])
    repos = discover_repos(workspace_with_repos, config)
    assert len(repos) == 1


def test_walk_files_include_exclude(workspace_with_repos: Path) -> None:
    repo = workspace_with_repos / "my-backend"
    files = walk_files(
        repo,
        include=["**/*.php", "**/*.go", "**/*.md"],
        exclude=["**/.git/**"],
    )
    names = {file_path.name for file_path in files}
    assert "AuthController.php" in names
    assert "main.go" in names
    assert "README.md" in names


def test_walk_files_excludes_git(workspace_with_repos: Path) -> None:
    repo = workspace_with_repos / "my-backend"
    files = walk_files(repo, include=["**/*"], exclude=["**/.git/**"])
    for file_path in files:
        assert ".git" not in file_path.parts


@patch("codebase_rag.indexer.core.embed_chunks")
def test_index_repo_creates_chunks(mock_embed, workspace_with_repos: Path) -> None:
    """Full index of a repo creates chunks in the store."""
    repo = workspace_with_repos / "my-backend"
    config = Config(
        include=["**/*.php", "**/*.go", "**/*.md", "**/.env.example"],
        exclude=["**/.git/**"],
    )
    store = LanceStore(workspace_with_repos)

    mock_embed.side_effect = lambda chunks, model: _make_fake_embeddings(len(chunks))

    stats = index_repo(repo_path=repo, config=config, store=store, full=True)

    assert stats.repo_name == "my-backend"
    assert stats.files_processed > 0
    assert stats.chunks_created > 0

    store_stats = store.get_stats()
    assert store_stats["total_chunks"] > 0


@patch("codebase_rag.indexer.core.embed_chunks")
def test_incremental_index_skips_unchanged(
    mock_embed, workspace_with_repos: Path
) -> None:
    """Second index run skips files that haven't changed."""
    repo = workspace_with_repos / "my-backend"
    config = Config(
        include=["**/*.php", "**/*.go", "**/*.md"],
        exclude=["**/.git/**"],
    )
    store = LanceStore(workspace_with_repos)
    mock_embed.side_effect = lambda chunks, model: _make_fake_embeddings(len(chunks))

    stats1 = index_repo(repo_path=repo, config=config, store=store, full=True)
    assert stats1.files_processed > 0

    stats2 = index_repo(repo_path=repo, config=config, store=store, full=False)
    assert stats2.files_processed == 0
    assert stats2.chunks_created == 0


@patch("codebase_rag.indexer.core.embed_chunks")
def test_index_workspace_end_to_end(mock_embed, workspace_with_repos: Path) -> None:
    """index_workspace discovers repos and indexes them."""
    config = Config(
        auto_discover=True,
        include=["**/*.php", "**/*.go", "**/*.md"],
        exclude=["**/.git/**"],
    )
    mock_embed.side_effect = lambda chunks, model: _make_fake_embeddings(len(chunks))

    stats = index_workspace(
        workspace_path=workspace_with_repos, config=config, full=True
    )

    assert stats.repos_indexed == 1
    assert stats.total_chunks > 0


@patch("codebase_rag.indexer.core.embed_chunks")
def test_structured_data_saved(mock_embed, workspace_with_repos: Path) -> None:
    """Structured data (env vars) is extracted and persisted."""
    repo = workspace_with_repos / "my-backend"
    config = Config(
        include=["**/*.php", "**/*.go", "**/*.md", "**/.env.example"],
        exclude=["**/.git/**"],
    )
    store = LanceStore(workspace_with_repos)
    mock_embed.side_effect = lambda chunks, model: _make_fake_embeddings(len(chunks))

    index_repo(repo_path=repo, config=config, store=store, full=True)

    env_data = store.load_structured("my-backend", "env")
    assert isinstance(env_data, list)
    names = [entry["name"] for entry in env_data]
    assert "DB_HOST" in names


@patch("codebase_rag.indexer.core.embed_chunks")
def test_summary_saved(mock_embed, workspace_with_repos: Path) -> None:
    """Repo summary is generated and saved."""
    repo = workspace_with_repos / "my-backend"
    config = Config(
        include=["**/*.php", "**/*.go", "**/*.md"],
        exclude=["**/.git/**"],
    )
    store = LanceStore(workspace_with_repos)
    mock_embed.side_effect = lambda chunks, model: _make_fake_embeddings(len(chunks))

    index_repo(repo_path=repo, config=config, store=store, full=True)

    summary = store.load_summary("my-backend")
    assert isinstance(summary, dict)
    assert summary["name"] == "my-backend"
    assert "stack" in summary
    assert "chunk_count" in summary
