from pathlib import Path

import pytest

from codebase_rag.store.lance import LanceStore, VECTOR_DIM


def make_chunks_and_embeddings(
    n: int, repo_name: str = "test-repo", language: str = "python"
) -> tuple[list[dict], list[list[float]]]:
    chunks: list[dict] = []
    embeddings: list[list[float]] = []
    for i in range(n):
        chunks.append(
            {
                "id": f"{repo_name}:file{i}.py:{i + 1}",
                "text": f"def function_{i}(): pass",
                "repo_name": repo_name,
                "file_path": f"file{i}.py",
                "abs_file_path": f"/workspace/file{i}.py",
                "start_line": i + 1,
                "end_line": i + 5,
                "language": language,
                "chunk_type": "function",
                "symbol_name": f"function_{i}",
                "file_mtime": 1700000000.0 + i,
            }
        )
        embeddings.append([0.1 * (i + 1)] * VECTOR_DIM)
    return chunks, embeddings


@pytest.fixture
def store(tmp_path: Path) -> LanceStore:
    return LanceStore(workspace_path=tmp_path / "workspace", data_dir=tmp_path / "data")


def test_store_creation(store: LanceStore) -> None:
    assert store.store_path.exists()


def test_upsert_chunks(store: LanceStore) -> None:
    chunks, embeddings = make_chunks_and_embeddings(5)
    inserted = store.upsert_chunks(chunks, embeddings)
    assert inserted == 5


def test_search_returns_results(store: LanceStore) -> None:
    chunks, embeddings = make_chunks_and_embeddings(5)
    store.upsert_chunks(chunks, embeddings)

    results = store.search(vector=[0.1] * VECTOR_DIM, limit=5)

    assert results
    assert "score" in results[0]
    assert isinstance(results[0]["score"], float)


def test_search_repo_filter(store: LanceStore) -> None:
    chunks_a, embeddings_a = make_chunks_and_embeddings(3, repo_name="repo-a")
    chunks_b, embeddings_b = make_chunks_and_embeddings(3, repo_name="repo-b")
    store.upsert_chunks(chunks_a, embeddings_a)
    store.upsert_chunks(chunks_b, embeddings_b)

    results = store.search(vector=[0.1] * VECTOR_DIM, filter_repos=["repo-a"], limit=10)

    assert results
    assert all(result["repo_name"] == "repo-a" for result in results)


def test_search_language_filter(store: LanceStore) -> None:
    chunks_py, embeddings_py = make_chunks_and_embeddings(3, language="python")
    chunks_go, embeddings_go = make_chunks_and_embeddings(
        3,
        repo_name="go-repo",
        language="go",
    )
    store.upsert_chunks(chunks_py, embeddings_py)
    store.upsert_chunks(chunks_go, embeddings_go)

    results = store.search(
        vector=[0.1] * VECTOR_DIM,
        filter_languages=["go"],
        limit=10,
    )

    assert results
    assert all(result["language"] == "go" for result in results)


def test_search_limit(store: LanceStore) -> None:
    chunks, embeddings = make_chunks_and_embeddings(10)
    store.upsert_chunks(chunks, embeddings)

    results = store.search(vector=[0.1] * VECTOR_DIM, limit=3)

    assert len(results) == 3


def test_search_empty_table(store: LanceStore) -> None:
    assert store.search(vector=[0.1] * VECTOR_DIM) == []


def test_delete_repo(store: LanceStore) -> None:
    chunks_a, embeddings_a = make_chunks_and_embeddings(3, repo_name="repo-a")
    chunks_b, embeddings_b = make_chunks_and_embeddings(2, repo_name="repo-b")
    store.upsert_chunks(chunks_a, embeddings_a)
    store.upsert_chunks(chunks_b, embeddings_b)

    deleted = store.delete_repo("repo-a")
    remaining = store.search(vector=[0.1] * VECTOR_DIM, limit=10)

    assert deleted == 3
    assert all(row["repo_name"] != "repo-a" for row in remaining)


def test_get_stats(store: LanceStore) -> None:
    chunks_a, embeddings_a = make_chunks_and_embeddings(3, repo_name="repo-a")
    chunks_b, embeddings_b = make_chunks_and_embeddings(
        2, repo_name="repo-b", language="go"
    )
    store.upsert_chunks(chunks_a, embeddings_a)
    store.upsert_chunks(chunks_b, embeddings_b)

    stats = store.get_stats()

    assert stats["total_chunks"] == 5
    assert stats["repos"] == ["repo-a", "repo-b"]
    assert stats["languages"] == ["go", "python"]


def test_get_stats_empty(store: LanceStore) -> None:
    assert store.get_stats() == {"total_chunks": 0, "repos": [], "languages": []}


def test_upsert_overwrites_existing(store: LanceStore) -> None:
    chunks, embeddings = make_chunks_and_embeddings(2)
    store.upsert_chunks(chunks, embeddings)

    updated_chunks = [{**chunk, "text": f"UPDATED {chunk['text']}"} for chunk in chunks]
    store.upsert_chunks(updated_chunks, embeddings)

    results = store.search(vector=[0.1] * VECTOR_DIM, limit=10)
    text_by_id = {result["id"]: result["text"] for result in results}

    for chunk in updated_chunks:
        assert text_by_id[chunk["id"]] == chunk["text"]


def test_save_load_structured(store: LanceStore) -> None:
    payload = {"routes": [{"method": "GET", "path": "/health"}]}
    store.save_structured("repo-a", "routes", payload)

    loaded = store.load_structured("repo-a", "routes")

    assert loaded == payload


def test_load_structured_missing(store: LanceStore) -> None:
    assert store.load_structured("repo-a", "missing") is None


def test_save_load_summary(store: LanceStore) -> None:
    summary = {"name": "repo-a", "stack": "python"}
    store.save_summary("repo-a", summary)

    loaded = store.load_summary("repo-a")

    assert loaded == summary


def test_load_all_summaries(store: LanceStore) -> None:
    summary_a = {"name": "repo-a", "stack": "python"}
    summary_b = {"name": "repo-b", "stack": "go"}
    store.save_summary("repo-a", summary_a)
    store.save_summary("repo-b", summary_b)

    loaded = store.load_summary()

    assert isinstance(loaded, list)
    by_name = {item["name"]: item for item in loaded}
    assert by_name["repo-a"] == summary_a
    assert by_name["repo-b"] == summary_b


def test_load_summary_missing(store: LanceStore) -> None:
    assert store.load_summary("does-not-exist") is None
