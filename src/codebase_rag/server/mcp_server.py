from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

from mcp.server.fastmcp import FastMCP

logger = logging.getLogger(__name__)

# Module-level server instance for MCP clients.
mcp = FastMCP("codebase-rag")


def _get_workspace() -> Path:
    """Get workspace path from environment variable."""
    workspace = os.getenv("CODEBASE_RAG_WORKSPACE")
    if not workspace:
        raise RuntimeError(
            "CODEBASE_RAG_WORKSPACE environment variable is not set. "
            "Set it in your MCP client config (e.g., .vscode/mcp.json)."
        )

    path = Path(workspace).expanduser().resolve()
    if not path.is_dir():
        raise RuntimeError(f"Workspace path does not exist: {path}")
    return path


def _get_engine():
    """Lazy-initialize search engine."""
    from codebase_rag.config import load_config
    from codebase_rag.search.engine import SearchEngine

    workspace = _get_workspace()
    config = load_config(workspace)
    return SearchEngine(
        workspace_path=workspace, embedding_model=config.embedding_model
    )


@mcp.tool()
def rag_search(
    query: str,
    repos: list[str] | None = None,
    filetypes: list[str] | None = None,
    limit: int = 10,
) -> str:
    """Semantic search across indexed codebases.

    Args:
            query: Natural language query or code snippet to search for.
            repos: Optional list of repository names to filter results.
            filetypes: Optional list of file extensions to filter (e.g., ["php", "go"]).
            limit: Maximum number of results to return (default: 10).
    """
    try:
        engine = _get_engine()
        results = engine.search(
            query=query, repos=repos, filetypes=filetypes, limit=limit
        )

        if not results:
            return "No results found. Make sure the workspace is indexed (codebase-rag index)."

        output: list[str] = []
        for i, result in enumerate(results, start=1):
            entry = (
                f"### Result {i} (score: {result.score:.3f})\n"
                f"**File**: {result.file_path} (lines {result.start_line}-{result.end_line})\n"
                f"**Repo**: {result.repo_name} | **Language**: {result.language} "
                f"| **Type**: {result.chunk_type}"
            )
            if result.symbol_name:
                entry += f" | **Symbol**: {result.symbol_name}"
            entry += f"\n```{result.language}\n{result.chunk_text}\n```"
            output.append(entry)

        return "\n\n".join(output)
    except Exception as exc:
        logger.exception("rag_search failed")
        return f"Error: {exc}"


@mcp.tool()
def rag_lookup(category: str, repo: str) -> str:
    """Look up structured data for a repository.

    Args:
            category: One of routes, migrations, env, docker, models.
            repo: Repository name.
    """
    try:
        engine = _get_engine()
        data = engine.lookup(category=category, repo=repo)
        if data is None:
            return (
                f"No {category} data found for repo '{repo}'. Make sure it is indexed."
            )
        return json.dumps(data, indent=2)
    except Exception as exc:
        logger.exception("rag_lookup failed")
        return f"Error: {exc}"


@mcp.tool()
def rag_summary(repo: str | None = None) -> str:
    """Get pre-computed overview data for indexed repositories.

    Args:
            repo: Specific repository name. If omitted, returns all repos.
    """
    try:
        engine = _get_engine()
        data = engine.summary(repo=repo)

        if data is None:
            message = (
                f"No summary found for repo '{repo}'."
                if repo
                else "No summaries found."
            )
            return f"{message} Make sure the workspace is indexed (codebase-rag index)."

        return json.dumps(data, indent=2)
    except Exception as exc:
        logger.exception("rag_summary failed")
        return f"Error: {exc}"


@mcp.tool()
def rag_reindex(repos: list[str] | None = None, full: bool = False) -> str:
    """Re-index specific repos or the entire workspace.

    Args:
            repos: Specific repository names to re-index. Omit for full workspace reindex.
            full: Force full reindex, ignoring file modification times.
    """
    try:
        from codebase_rag.config import load_config
        from codebase_rag.indexer.core import index_workspace

        workspace = _get_workspace()
        config = load_config(workspace)

        if repos:
            config.auto_discover = False
            config.repo_paths = repos

        stats = index_workspace(workspace_path=workspace, config=config, full=full)

        lines = [
            f"Indexed {stats.repos_indexed} repo(s) in {stats.duration_seconds:.1f}s",
            f"Files processed: {stats.total_files}",
            f"Chunks created: {stats.total_chunks}",
        ]
        for repo_stat in stats.repo_stats:
            lines.append(
                f"  - {repo_stat.repo_name}: {repo_stat.files_processed} files, "
                f"{repo_stat.chunks_created} chunks ({repo_stat.duration_seconds:.1f}s)"
            )

        return "\n".join(lines)
    except Exception as exc:
        logger.exception("rag_reindex failed")
        return f"Error: {exc}"


def run_server() -> None:
    """Start the MCP server on stdio transport."""
    # Never use stdout for logs in stdio mode; stdout is MCP JSON-RPC transport.
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        stream=sys.stderr,
    )
    logger.info("Starting codebase-rag MCP server")
    mcp.run(transport="stdio")
