from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import lancedb
import pyarrow as pa

logger = logging.getLogger(__name__)

DEFAULT_DATA_DIR = Path.home() / ".local" / "share" / "codebase-rag"
VECTOR_DIM = 768  # nomic-embed-text dimension


@dataclass(slots=True)
class _ChunkRow:
    id: str
    text: str
    repo_name: str
    file_path: str
    abs_file_path: str
    start_line: int
    end_line: int
    language: str
    chunk_type: str
    symbol_name: str | None
    file_mtime: float
    vector: list[float]


class LanceStore:
    def __init__(self, workspace_path: str | Path, data_dir: str | Path | None = None):
        """
        Initialize store for a workspace.
        - Compute workspace hash from absolute path: hashlib.sha256(str(path).encode()).hexdigest()[:16]
        - data_dir defaults to env var CODEBASE_RAG_DATA_DIR or DEFAULT_DATA_DIR
        - Store path: data_dir / "indexes" / workspace_hash
        - Create directories if needed
        - Open LanceDB connection: lancedb.connect(str(store_path))
        """
        workspace = Path(workspace_path).expanduser().resolve()
        workspace_hash = hashlib.sha256(str(workspace).encode()).hexdigest()[:16]

        base_data_dir = (
            Path(data_dir)
            if data_dir is not None
            else Path(os.getenv("CODEBASE_RAG_DATA_DIR", DEFAULT_DATA_DIR))
        )
        self._store_path = (
            base_data_dir.expanduser().resolve() / "indexes" / workspace_hash
        )
        self._store_path.mkdir(parents=True, exist_ok=True)

        self.db = lancedb.connect(str(self._store_path))

    @property
    def store_path(self) -> Path:
        return self._store_path

    def _open_chunks_table(self):
        try:
            return self.db.open_table("chunks")
        except Exception:
            return None

    @staticmethod
    def _sql_quote(value: str) -> str:
        return "'" + value.replace("'", "''") + "'"

    def upsert_chunks(self, chunks: list[dict], embeddings: list[list[float]]) -> int:
        if not chunks:
            return 0
        if len(chunks) != len(embeddings):
            raise ValueError("chunks and embeddings must have the same length")

        rows: list[_ChunkRow] = []
        for chunk, embedding in zip(chunks, embeddings, strict=True):
            if len(embedding) != VECTOR_DIM:
                raise ValueError(
                    f"embedding for chunk '{chunk.get('id', '<unknown>')}' has dimension "
                    f"{len(embedding)} but expected {VECTOR_DIM}"
                )
            rows.append(
                _ChunkRow(
                    id=str(chunk["id"]),
                    text=str(chunk["text"]),
                    repo_name=str(chunk["repo_name"]),
                    file_path=str(chunk["file_path"]),
                    abs_file_path=str(chunk["abs_file_path"]),
                    start_line=int(chunk["start_line"]),
                    end_line=int(chunk["end_line"]),
                    language=str(chunk["language"]),
                    chunk_type=str(chunk["chunk_type"]),
                    symbol_name=(
                        str(chunk["symbol_name"])
                        if chunk.get("symbol_name") is not None
                        else None
                    ),
                    file_mtime=float(chunk["file_mtime"]),
                    vector=[float(v) for v in embedding],
                )
            )

        schema = pa.schema(
            [
                pa.field("id", pa.string()),
                pa.field("text", pa.string()),
                pa.field("repo_name", pa.string()),
                pa.field("file_path", pa.string()),
                pa.field("abs_file_path", pa.string()),
                pa.field("start_line", pa.int32()),
                pa.field("end_line", pa.int32()),
                pa.field("language", pa.string()),
                pa.field("chunk_type", pa.string()),
                pa.field("symbol_name", pa.string()),
                pa.field("file_mtime", pa.float64()),
                pa.field("vector", pa.list_(pa.float32(), VECTOR_DIM)),
            ]
        )

        data = pa.table(
            {
                "id": [row.id for row in rows],
                "text": [row.text for row in rows],
                "repo_name": [row.repo_name for row in rows],
                "file_path": [row.file_path for row in rows],
                "abs_file_path": [row.abs_file_path for row in rows],
                "start_line": [row.start_line for row in rows],
                "end_line": [row.end_line for row in rows],
                "language": [row.language for row in rows],
                "chunk_type": [row.chunk_type for row in rows],
                "symbol_name": [row.symbol_name for row in rows],
                "file_mtime": [row.file_mtime for row in rows],
                "vector": [row.vector for row in rows],
            },
            schema=schema,
        )

        table = self._open_chunks_table()
        if table is None:
            self.db.create_table("chunks", data)
            return len(rows)

        ids_sql = ", ".join(self._sql_quote(row.id) for row in rows)
        table.delete(f"id IN ({ids_sql})")
        table.add(data)
        return len(rows)

    def search(
        self,
        vector: list[float],
        filter_repos: list[str] | None = None,
        filter_languages: list[str] | None = None,
        limit: int = 10,
    ) -> list[dict]:
        table = self._open_chunks_table()
        if table is None:
            return []

        query = table.search(vector).limit(limit)

        filters: list[str] = []
        if filter_repos:
            repos = ", ".join(self._sql_quote(repo) for repo in filter_repos)
            filters.append(f"repo_name IN ({repos})")
        if filter_languages:
            languages = ", ".join(
                self._sql_quote(language) for language in filter_languages
            )
            filters.append(f"language IN ({languages})")
        if filters:
            query = query.where(" AND ".join(filters))

        results = query.to_list()
        for row in results:
            distance = float(row.get("_distance", 0.0))
            row["score"] = 1.0 / (1.0 + distance)

        results.sort(key=lambda item: item["score"], reverse=True)
        return results

    def delete_repo(self, repo_name: str) -> int:
        table = self._open_chunks_table()
        if table is None:
            return 0

        where = f"repo_name = {self._sql_quote(repo_name)}"
        delete_result = table.delete(where)
        return int(getattr(delete_result, "num_deleted_rows", 0))

    def get_stats(self) -> dict:
        table = self._open_chunks_table()
        if table is None:
            return {"total_chunks": 0, "repos": [], "languages": []}

        total_chunks = int(table.count_rows())
        arrow_table = table.to_arrow()

        repos_col = (
            arrow_table.column("repo_name").to_pylist()
            if "repo_name" in arrow_table.column_names
            else []
        )
        languages_col = (
            arrow_table.column("language").to_pylist()
            if "language" in arrow_table.column_names
            else []
        )

        repos = sorted({str(value) for value in repos_col if value is not None})
        languages = sorted({str(value) for value in languages_col if value is not None})

        return {
            "total_chunks": total_chunks,
            "repos": repos,
            "languages": languages,
        }

    def save_structured(self, repo_name: str, category: str, data: dict | list) -> None:
        path = self.store_path / "structured" / repo_name / f"{category}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")

    def load_structured(self, repo_name: str, category: str) -> dict | list | None:
        path = self.store_path / "structured" / repo_name / f"{category}.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def save_summary(self, repo_name: str, summary: dict) -> None:
        path = self.store_path / "summaries" / f"{repo_name}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")

    def load_summary(self, repo_name: str | None = None) -> dict | list[dict] | None:
        summaries_dir = self.store_path / "summaries"

        if repo_name is not None:
            summary_path = summaries_dir / f"{repo_name}.json"
            if not summary_path.exists():
                return None
            return json.loads(summary_path.read_text(encoding="utf-8"))

        if not summaries_dir.exists():
            return None

        summaries: list[dict[str, Any]] = []
        for summary_file in sorted(summaries_dir.glob("*.json")):
            summaries.append(json.loads(summary_file.read_text(encoding="utf-8")))

        return summaries or None
