from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class RepoProfile:
    name: str
    path: str
    stack: str
    language: str
    framework: str
    key_paths: dict[str, str] = field(default_factory=dict)


def detect_stack(repo_path: str | Path) -> RepoProfile:
    """Detect the repository stack from marker files and directories."""
    root = Path(repo_path).resolve()
    key_paths: dict[str, str] = {}

    logger.debug("Detecting stack for repo: %s", root)

    if (root / "composer.json").is_file() and (root / "artisan").exists():
        key_paths.update(
            {
                "routes": "routes/api.php",
                "migrations": "database/migrations",
                "models": "app/Models",
                "controllers": "app/Http/Controllers",
                "env": ".env.example",
                "docker": "docker-compose.yml",
                "tests": "tests",
            }
        )
        return _build_profile(root, "laravel", "php", "Laravel", key_paths)

    if (root / "composer.json").is_file():
        key_paths.update(
            {
                "env": ".env.example",
                "docker": "docker-compose.yml",
                "tests": "tests",
            }
        )
        return _build_profile(root, "php", "php", "Generic PHP", key_paths)

    if (root / "go.mod").is_file() and (root / "internal" / "server").is_dir():
        key_paths.update(
            {
                "docker": "docker-compose.yml",
                "tests": "tests",
            }
        )
        if (root / "cmd").is_dir():
            key_paths["cmd"] = "cmd"
        if (root / "internal").is_dir():
            key_paths["internal"] = "internal"
        return _build_profile(root, "go-chi", "go", "Chi", key_paths)

    if (root / "go.mod").is_file():
        key_paths.update(
            {
                "docker": "docker-compose.yml",
                "tests": "tests",
            }
        )
        return _build_profile(root, "go", "go", "Generic Go", key_paths)

    if (root / "package.json").is_file() and _has_vue_files(root):
        key_paths.update(
            {
                "env": ".env.example",
                "docker": "docker-compose.yml",
                "tests": "tests",
            }
        )
        return _build_profile(root, "vue", "typescript", "Vue 3", key_paths)

    if (root / "package.json").is_file() and _has_next_config(root):
        return _build_profile(root, "nextjs", "typescript", "Next.js", key_paths)

    if (root / "package.json").is_file() and _has_nuxt_config(root):
        return _build_profile(root, "nuxt", "typescript", "Nuxt", key_paths)

    if (root / "package.json").is_file():
        return _build_profile(root, "node", "javascript", "Node.js", key_paths)

    if (root / "Cargo.toml").is_file():
        return _build_profile(root, "rust", "rust", "Rust", key_paths)

    if _has_dotnet_markers(root):
        return _build_profile(root, "dotnet", "csharp", ".NET", key_paths)

    if _has_java_markers(root):
        return _build_profile(root, "java", "java", "Java", key_paths)

    return _build_profile(root, "unknown", "unknown", "Unknown", key_paths)


def _build_profile(
    root: Path,
    stack: str,
    language: str,
    framework: str,
    key_paths: dict[str, str],
) -> RepoProfile:
    merged_paths = dict(key_paths)
    _add_common_key_paths(root, merged_paths)
    profile = RepoProfile(
        name=root.name,
        path=str(root),
        stack=stack,
        language=language,
        framework=framework,
        key_paths=merged_paths,
    )
    logger.debug("Detected repo profile: %s", profile)
    return profile


def _add_common_key_paths(root: Path, key_paths: dict[str, str]) -> None:
    if (root / ".env.example").is_file():
        key_paths["env"] = ".env.example"
    if (root / "docker-compose.yml").is_file():
        key_paths["docker"] = "docker-compose.yml"


def _has_vue_files(root: Path) -> bool:
    return any(root.rglob("*.vue"))


def _has_next_config(root: Path) -> bool:
    return any(root.glob("next.config.*"))


def _has_nuxt_config(root: Path) -> bool:
    return any(root.glob("nuxt.config.*"))


def _has_dotnet_markers(root: Path) -> bool:
    return any(root.rglob("*.csproj")) or any(root.rglob("*.sln"))


def _has_java_markers(root: Path) -> bool:
    return (root / "pom.xml").is_file() or any(root.glob("build.gradle*"))
