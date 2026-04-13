from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

import click

logger = logging.getLogger(__name__)


def _get_workspace() -> Path:
    """Resolve workspace from env var or cwd."""
    workspace = os.getenv("CODEBASE_RAG_WORKSPACE", os.getcwd())
    return Path(workspace).expanduser().resolve()


@click.group()
def main() -> None:
    """codebase-rag - Local RAG-powered MCP server for codebase-aware AI assistants."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        stream=sys.stderr,
    )


@main.command()
def init() -> None:
    """Initialize workspace: create .copilot-rag.yaml and .vscode/mcp.json."""
    from codebase_rag.config import save_config

    workspace = _get_workspace()

    config_path = save_config(workspace)
    click.echo(f"Created {config_path}")

    vscode_dir = workspace / ".vscode"
    vscode_dir.mkdir(exist_ok=True)
    mcp_json_path = vscode_dir / "mcp.json"

    mcp_config: dict = {
        "servers": {
            "codebase-rag": {
                "type": "stdio",
                "command": "uvx",
                "args": ["--from", "codebase-rag", "codebase-rag", "serve"],
                "env": {
                    "CODEBASE_RAG_WORKSPACE": "${workspaceFolder}",
                },
            }
        }
    }

    if mcp_json_path.exists():
        try:
            existing = json.loads(mcp_json_path.read_text(encoding="utf-8"))
            existing.setdefault("servers", {})["codebase-rag"] = mcp_config["servers"][
                "codebase-rag"
            ]
            mcp_config = existing
        except (json.JSONDecodeError, OSError):
            logger.warning("Could not read existing %s; rewriting", mcp_json_path)

    mcp_json_path.write_text(json.dumps(mcp_config, indent=2), encoding="utf-8")
    click.echo(f"Created {mcp_json_path}")


@main.command()
@click.option("--full", is_flag=True, help="Force full reindex (ignore file mtimes).")
@click.option("--repo", default=None, help="Index a specific repo only.")
def index(full: bool, repo: str | None) -> None:
    """Index the workspace (incremental by default)."""
    from codebase_rag.config import load_config
    from codebase_rag.indexer.core import index_workspace

    workspace = _get_workspace()
    config = load_config(workspace)

    if repo:
        config.auto_discover = False
        config.repo_paths = [repo]

    click.echo(f"Indexing workspace: {workspace}")
    stats = index_workspace(workspace_path=workspace, config=config, full=full)

    click.echo(f"\nIndexed {stats.repos_indexed} repo(s) in {stats.duration_seconds:.1f}s")
    click.echo(f"Files processed: {stats.total_files}")
    click.echo(f"Chunks created: {stats.total_chunks}")
    for repo_stat in stats.repo_stats:
        click.echo(
            f"  - {repo_stat.repo_name}: {repo_stat.files_processed} files, "
            f"{repo_stat.chunks_created} chunks ({repo_stat.duration_seconds:.1f}s)"
        )


@main.command()
@click.argument("query")
@click.option("--repo", default=None, help="Filter to a specific repo.")
@click.option("--limit", default=10, type=int, help="Max results.")
def search(query: str, repo: str | None, limit: int) -> None:
    """Search indexed codebases."""
    from codebase_rag.config import load_config
    from codebase_rag.search.engine import SearchEngine

    workspace = _get_workspace()
    config = load_config(workspace)
    engine = SearchEngine(workspace_path=workspace, embedding_model=config.embedding_model)

    repos = [repo] if repo else None
    results = engine.search(query=query, repos=repos, limit=limit)

    if not results:
        click.echo("No results found.")
        return

    for index_number, result in enumerate(results, start=1):
        click.echo(f"\n--- Result {index_number} (score: {result.score:.3f}) ---")
        click.echo(f"File: {result.file_path} (lines {result.start_line}-{result.end_line})")
        click.echo(
            f"Repo: {result.repo_name} | Language: {result.language} | Type: {result.chunk_type}"
        )
        if result.symbol_name:
            click.echo(f"Symbol: {result.symbol_name}")
        click.echo(result.chunk_text)


@main.command()
def stats() -> None:
    """Show index statistics."""
    from codebase_rag.store.lance import LanceStore

    workspace = _get_workspace()
    store = LanceStore(workspace)
    store_stats = store.get_stats()

    click.echo(f"Workspace: {workspace}")
    click.echo(f"Total chunks: {store_stats['total_chunks']}")
    click.echo(f"Repos: {', '.join(store_stats['repos']) or 'none'}")
    click.echo(f"Languages: {', '.join(store_stats['languages']) or 'none'}")


@main.command()
def serve() -> None:
    """Start MCP server (stdio transport)."""
    workspace = _get_workspace()
    os.environ.setdefault("CODEBASE_RAG_WORKSPACE", str(workspace))

    from codebase_rag.server.mcp_server import run_server

    run_server()
