from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import ollama as ollama_client

from codebase_rag.store.lance import LanceStore

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    chunk_text: str
    file_path: str
    repo_name: str
    start_line: int
    end_line: int
    language: str
    chunk_type: str
    symbol_name: str | None
    score: float


class SearchEngine:
    def __init__(self, workspace_path: str | Path, embedding_model: str = "nomic-embed-text"):
        self._store = LanceStore(workspace_path)
        self._embedding_model = embedding_model

    @property
    def store(self) -> LanceStore:
        return self._store

    def _embed_query(self, query: str) -> list[float]:
        """Embed a single query string using Ollama."""
        client = ollama_client.Client()
        response = client.embed(model=self._embedding_model, input=[query])
        embeddings = getattr(response, "embeddings", None)
        if embeddings is None and isinstance(response, dict):
            embeddings = response.get("embeddings")
        if not embeddings:
            raise RuntimeError("Failed to get embedding for query")
        return embeddings[0]

    def search(
        self,
        query: str,
        repos: list[str] | None = None,
        filetypes: list[str] | None = None,
        limit: int = 10,
    ) -> list[SearchResult]:
        """Semantic search across indexed repos."""
        query_vector = self._embed_query(query)
        raw_results = self._store.search(
            vector=query_vector,
            filter_repos=repos,
            filter_languages=filetypes,
            limit=limit,
        )
        return [
            SearchResult(
                chunk_text=row.get("text", ""),
                file_path=row.get("abs_file_path", row.get("file_path", "")),
                repo_name=row.get("repo_name", ""),
                start_line=int(row.get("start_line", 0)),
                end_line=int(row.get("end_line", 0)),
                language=row.get("language", ""),
                chunk_type=row.get("chunk_type", ""),
                symbol_name=row.get("symbol_name"),
                score=float(row.get("score", 0.0)),
            )
            for row in raw_results
        ]

    def lookup(self, category: str, repo: str) -> dict | list | None:
        """Direct structured data retrieval - no vector search."""
        return self._store.load_structured(repo, category)

    def summary(self, repo: str | None = None) -> dict | list[dict] | None:
        """Return pre-computed repo summary."""
        return self._store.load_summary(repo)
