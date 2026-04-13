from __future__ import annotations

import asyncio
import json
from unittest.mock import MagicMock, patch


def _registered_tool_names(mcp_obj: object) -> set[str]:
    """Return registered FastMCP tool names across supported APIs."""
    list_tools = getattr(mcp_obj, "list_tools", None)
    if callable(list_tools):
        tools = asyncio.run(list_tools())
        return {getattr(tool, "name", "") for tool in tools if getattr(tool, "name", "")}

    tool_manager = getattr(mcp_obj, "_tool_manager", None)
    if tool_manager is not None:
        tools = getattr(tool_manager, "_tools", {})
        if isinstance(tools, dict):
            return set(tools.keys())

    return set()


def test_server_has_four_tools() -> None:
    """The FastMCP server registers the expected four tools."""
    from codebase_rag.server.mcp_server import mcp

    tool_names = _registered_tool_names(mcp)

    assert "rag_search" in tool_names
    assert "rag_lookup" in tool_names
    assert "rag_summary" in tool_names
    assert "rag_reindex" in tool_names


def test_rag_search_returns_results(tmp_path, monkeypatch) -> None:
    """rag_search returns formatted results when engine has data."""
    monkeypatch.setenv("CODEBASE_RAG_WORKSPACE", str(tmp_path))

    mock_result = MagicMock()
    mock_result.chunk_text = "def login():"
    mock_result.file_path = "/repo/auth.py"
    mock_result.repo_name = "backend"
    mock_result.start_line = 10
    mock_result.end_line = 20
    mock_result.language = "python"
    mock_result.chunk_type = "function"
    mock_result.symbol_name = "login"
    mock_result.score = 0.95

    mock_engine = MagicMock()
    mock_engine.search.return_value = [mock_result]

    with patch("codebase_rag.server.mcp_server._get_engine", return_value=mock_engine):
        from codebase_rag.server.mcp_server import rag_search

        result = rag_search(query="authentication")

    assert "login" in result
    assert "0.95" in result or "0.950" in result
    assert "backend" in result


def test_rag_search_empty_results(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CODEBASE_RAG_WORKSPACE", str(tmp_path))

    mock_engine = MagicMock()
    mock_engine.search.return_value = []

    with patch("codebase_rag.server.mcp_server._get_engine", return_value=mock_engine):
        from codebase_rag.server.mcp_server import rag_search

        result = rag_search(query="nothing")

    assert "No results" in result


def test_rag_lookup_returns_json(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CODEBASE_RAG_WORKSPACE", str(tmp_path))

    mock_engine = MagicMock()
    mock_engine.lookup.return_value = [{"method": "POST", "path": "/login"}]

    with patch("codebase_rag.server.mcp_server._get_engine", return_value=mock_engine):
        from codebase_rag.server.mcp_server import rag_lookup

        result = rag_lookup(category="routes", repo="backend")

    parsed = json.loads(result)
    assert isinstance(parsed, list)
    assert parsed[0]["method"] == "POST"


def test_rag_lookup_missing_data(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CODEBASE_RAG_WORKSPACE", str(tmp_path))

    mock_engine = MagicMock()
    mock_engine.lookup.return_value = None

    with patch("codebase_rag.server.mcp_server._get_engine", return_value=mock_engine):
        from codebase_rag.server.mcp_server import rag_lookup

        result = rag_lookup(category="routes", repo="missing")

    assert "No routes data found" in result


def test_rag_summary_single_repo(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CODEBASE_RAG_WORKSPACE", str(tmp_path))

    mock_engine = MagicMock()
    mock_engine.summary.return_value = {"name": "backend", "stack": "python"}

    with patch("codebase_rag.server.mcp_server._get_engine", return_value=mock_engine):
        from codebase_rag.server.mcp_server import rag_summary

        result = rag_summary(repo="backend")

    parsed = json.loads(result)
    assert parsed["name"] == "backend"


def test_rag_summary_all_repos(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CODEBASE_RAG_WORKSPACE", str(tmp_path))

    mock_engine = MagicMock()
    mock_engine.summary.return_value = [{"name": "backend"}, {"name": "frontend"}]

    with patch("codebase_rag.server.mcp_server._get_engine", return_value=mock_engine):
        from codebase_rag.server.mcp_server import rag_summary

        result = rag_summary()

    parsed = json.loads(result)
    assert len(parsed) == 2


def test_rag_summary_missing(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CODEBASE_RAG_WORKSPACE", str(tmp_path))

    mock_engine = MagicMock()
    mock_engine.summary.return_value = None

    with patch("codebase_rag.server.mcp_server._get_engine", return_value=mock_engine):
        from codebase_rag.server.mcp_server import rag_summary

        result = rag_summary(repo="missing")

    assert "No summary found" in result


def test_rag_reindex(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CODEBASE_RAG_WORKSPACE", str(tmp_path))

    mock_stats = MagicMock()
    mock_stats.repos_indexed = 1
    mock_stats.total_files = 5
    mock_stats.total_chunks = 20
    mock_stats.duration_seconds = 1.5

    mock_repo_stat = MagicMock()
    mock_repo_stat.repo_name = "backend"
    mock_repo_stat.files_processed = 5
    mock_repo_stat.chunks_created = 20
    mock_repo_stat.duration_seconds = 1.5
    mock_stats.repo_stats = [mock_repo_stat]

    with patch("codebase_rag.config.load_config") as mock_load:
        mock_load.return_value = MagicMock()
        with patch(
            "codebase_rag.indexer.core.index_workspace",
            return_value=mock_stats,
        ):
            from codebase_rag.server.mcp_server import rag_reindex

            result = rag_reindex()

    assert "1 repo" in result
    assert "20" in result


def test_rag_search_handles_error(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CODEBASE_RAG_WORKSPACE", str(tmp_path))

    with patch(
        "codebase_rag.server.mcp_server._get_engine",
        side_effect=RuntimeError("Ollama not running"),
    ):
        from codebase_rag.server.mcp_server import rag_search

        result = rag_search(query="test")

    assert "Error" in result
    assert "Ollama not running" in result
