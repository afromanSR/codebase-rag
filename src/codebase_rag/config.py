from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

CONFIG_FILENAME = ".copilot-rag.yaml"

DEFAULT_INCLUDE = [
    "**/*.php",
    "**/*.go",
    "**/*.ts",
    "**/*.tsx",
    "**/*.vue",
    "**/*.md",
    "**/*.yaml",
    "**/*.yml",
    "**/*.json",
    "**/routes/**",
    "**/migrations/**",
    "**/.env.example",
    "**/docker-compose*.yml",
]

DEFAULT_EXCLUDE = [
    "**/vendor/**",
    "**/node_modules/**",
    "**/.rag/**",
    "**/storage/**",
    "**/dist/**",
    "**/build/**",
    "**/.git/**",
    "**/docs/swagger*",
    "**/public/docs/**",
]


@dataclass
class Config:
    version: int = 1
    embedding_model: str = "nomic-embed-text"
    auto_discover: bool = True
    repo_paths: list[str] = field(default_factory=list)
    include: list[str] = field(default_factory=lambda: list(DEFAULT_INCLUDE))
    exclude: list[str] = field(default_factory=lambda: list(DEFAULT_EXCLUDE))
    max_tokens: int = 512
    overlap_tokens: int = 64


def load_config(workspace_path: str | Path) -> Config:
    """Load config from .copilot-rag.yaml in workspace root. Returns defaults if not found."""
    config_path = Path(workspace_path) / CONFIG_FILENAME
    if not config_path.exists():
        logger.info("No config file found at %s, using defaults", config_path)
        return Config()

    try:
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        logger.warning(
            "Failed to parse config %s: %s — using defaults", config_path, exc
        )
        return Config()

    repos = raw.get("repos", {}) or {}
    index = raw.get("index", {}) or {}
    chunking = raw.get("chunking", {}) or {}

    return Config(
        version=int(raw.get("version", 1)),
        embedding_model=str(raw.get("embedding_model", "nomic-embed-text")),
        auto_discover=bool(repos.get("auto_discover", True)),
        repo_paths=list(repos.get("paths", [])),
        include=list(index.get("include", DEFAULT_INCLUDE)),
        exclude=list(index.get("exclude", DEFAULT_EXCLUDE)),
        max_tokens=int(chunking.get("max_tokens", 512)),
        overlap_tokens=int(chunking.get("overlap_tokens", 64)),
    )


def save_config(workspace_path: str | Path, config: Config | None = None) -> Path:
    """Save config to .copilot-rag.yaml. Creates default config if none provided."""
    if config is None:
        config = Config()

    config_path = Path(workspace_path) / CONFIG_FILENAME

    data: dict = {
        "version": config.version,
        "embedding_model": config.embedding_model,
        "repos": {"auto_discover": config.auto_discover},
        "index": {
            "include": config.include,
            "exclude": config.exclude,
        },
        "chunking": {
            "max_tokens": config.max_tokens,
            "overlap_tokens": config.overlap_tokens,
        },
    }

    if config.repo_paths:
        data["repos"]["paths"] = config.repo_paths

    config_path.write_text(
        yaml.dump(data, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )
    logger.info("Saved config to %s", config_path)
    return config_path
