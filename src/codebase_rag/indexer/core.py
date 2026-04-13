from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass, field
from fnmatch import fnmatch
from pathlib import Path

import ollama as ollama_client

from codebase_rag.config import Config
from codebase_rag.indexer.chunkers import Chunk, chunk_file
from codebase_rag.indexer.detector import RepoProfile, detect_stack
from codebase_rag.indexer.extractors import extract_structured
from codebase_rag.store.lance import LanceStore

logger = logging.getLogger(__name__)

EMBED_BATCH_SIZE = 100
MAX_FILE_SIZE_BYTES = 1024 * 1024


@dataclass
class RepoIndexStats:
    repo_name: str
    files_processed: int
    chunks_created: int
    duration_seconds: float


@dataclass
class IndexStats:
    repos_indexed: int
    total_files: int
    total_chunks: int
    duration_seconds: float
    repo_stats: list[RepoIndexStats] = field(default_factory=list)


def discover_repos(workspace_path: str | Path, config: Config) -> list[Path]:
    workspace = Path(workspace_path).expanduser().resolve()
    repos: list[Path] = []
    seen: set[Path] = set()

    def _add_repo(path: Path) -> None:
        resolved = path.expanduser().resolve()
        if not resolved.exists() or not resolved.is_dir():
            return
        if resolved in seen:
            return
        seen.add(resolved)
        repos.append(resolved)

    if config.auto_discover:
        if (workspace / ".git").is_dir():
            _add_repo(workspace)

        for child in workspace.iterdir():
            if not child.is_dir():
                continue
            if (child / ".git").is_dir():
                _add_repo(child)

    for repo_entry in config.repo_paths:
        repo_path = Path(repo_entry)
        if not repo_path.is_absolute():
            repo_path = workspace / repo_path
        _add_repo(repo_path)

    return sorted(repos)


def _matches_any_pattern(relative_path: str, patterns: list[str]) -> bool:
    if not patterns:
        return False

    for pattern in patterns:
        if fnmatch(relative_path, pattern):
            return True
        # Allow "**/x" patterns to match root-level paths like "x".
        if pattern.startswith("**/") and fnmatch(relative_path, pattern[3:]):
            return True
    return False


def walk_files(repo_path: Path, include: list[str], exclude: list[str]) -> list[Path]:
    root = repo_path.expanduser().resolve()
    files: list[Path] = []

    for candidate in root.rglob("*"):
        if not candidate.is_file():
            continue

        try:
            relative_path = candidate.relative_to(root).as_posix()
        except ValueError:
            continue

        if include and not _matches_any_pattern(relative_path, include):
            continue
        if exclude and _matches_any_pattern(relative_path, exclude):
            continue

        try:
            if candidate.stat().st_size > MAX_FILE_SIZE_BYTES:
                continue
        except OSError:
            continue

        files.append(candidate.resolve())

    return sorted(files)


def embed_chunks(chunks: list[Chunk], model: str) -> list[list[float]]:
    if not chunks:
        return []

    client = ollama_client.Client()
    embeddings: list[list[float]] = []

    for offset in range(0, len(chunks), EMBED_BATCH_SIZE):
        batch = chunks[offset : offset + EMBED_BATCH_SIZE]
        texts = [chunk.text for chunk in batch]
        try:
            response = client.embed(model=model, input=texts)
        except Exception:
            logger.exception(
                "Failed to embed chunk batch (%d-%d) with model '%s'",
                offset,
                offset + len(batch) - 1,
                model,
            )
            raise

        batch_embeddings = getattr(response, "embeddings", None)
        if batch_embeddings is None and isinstance(response, dict):
            batch_embeddings = response.get("embeddings")
        if not isinstance(batch_embeddings, list):
            raise RuntimeError("Ollama embed response missing embeddings list")

        embeddings.extend(batch_embeddings)

    if len(embeddings) != len(chunks):
        raise RuntimeError(
            f"Embedding count mismatch: expected {len(chunks)}, got {len(embeddings)}"
        )

    return embeddings


def _load_metadata(store: LanceStore) -> dict:
    metadata_path = store.store_path / "metadata.json"
    if not metadata_path.exists():
        return {}

    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.exception("Failed to load metadata from %s", metadata_path)
        return {}

    if not isinstance(metadata, dict):
        return {}

    file_mtimes = metadata.get("file_mtimes")
    if not isinstance(file_mtimes, dict):
        metadata["file_mtimes"] = {}

    file_chunk_counts = metadata.get("file_chunk_counts")
    if not isinstance(file_chunk_counts, dict):
        metadata["file_chunk_counts"] = {}

    return metadata


def _save_metadata(store: LanceStore, metadata: dict) -> None:
    metadata_path = store.store_path / "metadata.json"
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(
        json.dumps(metadata, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def index_repo(
    repo_path: Path,
    config: Config,
    store: LanceStore,
    full: bool = False,
) -> RepoIndexStats:
    start = time.time()
    repo = repo_path.expanduser().resolve()
    profile = detect_stack(repo)

    all_files = walk_files(repo, config.include, config.exclude)
    metadata = _load_metadata(store)
    stored_mtimes = metadata.setdefault("file_mtimes", {})
    stored_chunk_counts = metadata.setdefault("file_chunk_counts", {})

    repo_files_map: dict[str, Path] = {str(path): path for path in all_files}
    repo_file_keys = set(repo_files_map.keys())
    tracked_repo_files = {
        path_key
        for path_key in stored_mtimes
        if str(repo) == path_key or path_key.startswith(f"{repo}/")
    }

    if full:
        files_to_process = all_files
        store.delete_repo(profile.name)
    else:
        files_to_process = []
        for path_key, path_obj in repo_files_map.items():
            current_mtime = path_obj.stat().st_mtime
            if stored_mtimes.get(path_key) != current_mtime:
                files_to_process.append(path_obj)

    chunks: list[Chunk] = []
    for file_path in files_to_process:
        try:
            chunks.extend(
                chunk_file(
                    file_path=file_path,
                    repo_name=profile.name,
                    repo_path=repo,
                    max_tokens=config.max_tokens,
                    overlap_tokens=config.overlap_tokens,
                )
            )
        except Exception:
            logger.exception("Failed to chunk file: %s", file_path)

    if chunks:
        chunk_payloads = [asdict(chunk) for chunk in chunks]
        embeddings = embed_chunks(chunks, model=config.embedding_model)
        store.upsert_chunks(chunk_payloads, embeddings)

    structured = extract_structured(repo, profile.stack)
    for category, data in structured.items():
        store.save_structured(profile.name, category, data)

    # Keep per-file incremental metadata for skip logic and summary chunk count.
    for path_key in tracked_repo_files - repo_file_keys:
        stored_mtimes.pop(path_key, None)
        stored_chunk_counts.pop(path_key, None)

    chunks_by_file: dict[str, int] = {}
    for chunk in chunks:
        chunks_by_file[chunk.abs_file_path] = (
            chunks_by_file.get(chunk.abs_file_path, 0) + 1
        )

    for path_key, path_obj in repo_files_map.items():
        stored_mtimes[path_key] = path_obj.stat().st_mtime
        if full or path_obj in files_to_process:
            stored_chunk_counts[path_key] = chunks_by_file.get(path_key, 0)

    _save_metadata(store, metadata)

    repo_chunk_count = sum(
        count
        for path_key, count in stored_chunk_counts.items()
        if str(repo) == path_key or path_key.startswith(f"{repo}/")
    )

    summary_chunks = chunks
    if not summary_chunks and hasattr(store, "load_summary"):
        existing_summary = store.load_summary(profile.name)
        if isinstance(existing_summary, dict) and isinstance(
            existing_summary.get("chunk_count"), int
        ):
            repo_chunk_count = int(existing_summary["chunk_count"])

    summary = _build_summary(profile, summary_chunks, structured)
    summary["chunk_count"] = repo_chunk_count
    store.save_summary(profile.name, summary)

    duration = time.time() - start
    return RepoIndexStats(
        repo_name=profile.name,
        files_processed=len(files_to_process),
        chunks_created=len(chunks),
        duration_seconds=duration,
    )


def index_workspace(
    workspace_path: str | Path,
    config: Config,
    full: bool = False,
) -> IndexStats:
    start = time.time()
    workspace = Path(workspace_path).expanduser().resolve()
    repos = discover_repos(workspace, config)
    store = LanceStore(workspace)

    repo_stats: list[RepoIndexStats] = []
    for repo_path in repos:
        repo_stats.append(
            index_repo(repo_path=repo_path, config=config, store=store, full=full)
        )

    total_files = sum(stat.files_processed for stat in repo_stats)
    total_chunks = sum(stat.chunks_created for stat in repo_stats)

    return IndexStats(
        repos_indexed=len(repo_stats),
        total_files=total_files,
        total_chunks=total_chunks,
        duration_seconds=time.time() - start,
        repo_stats=repo_stats,
    )


def _build_summary(profile: RepoProfile, chunks: list[Chunk], structured: dict) -> dict:
    routes = structured.get("routes")
    models = structured.get("models")

    endpoints_count = len(routes) if isinstance(routes, list) else 0
    models_list = models if isinstance(models, list) else []

    return {
        "name": profile.name,
        "stack": profile.stack,
        "framework": profile.framework,
        "key_files": profile.key_paths,
        "models": models_list,
        "endpoints_count": endpoints_count,
        "chunk_count": len(chunks),
        "last_indexed": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
