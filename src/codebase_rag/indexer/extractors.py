from __future__ import annotations

import logging
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


@dataclass
class RouteInfo:
    method: str
    path: str
    handler: str
    middleware: list[str] = field(default_factory=list)
    name: str | None = None


@dataclass
class MigrationInfo:
    file_name: str
    table_name: str
    columns: list[str] = field(default_factory=list)


@dataclass
class EnvVar:
    name: str
    default: str
    comment: str


@dataclass
class DockerService:
    name: str
    image: str
    ports: list[str] = field(default_factory=list)
    environment: list[str] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)


@dataclass
class DockerComposeInfo:
    services: list[DockerService] = field(default_factory=list)


_LARAVEL_ROUTE_RE = re.compile(
    r"Route::(get|post|put|delete|patch)\s*\(\s*['\"]([^'\"]+)['\"]\s*,\s*(.+?)\)\s*;",
    re.IGNORECASE,
)
_LARAVEL_RESOURCE_RE = re.compile(
    r"Route::resource\s*\(\s*['\"]([^'\"]+)['\"]\s*,\s*(.+?)\)\s*;",
    re.IGNORECASE,
)
_LARAVEL_MIDDLEWARE_GROUP_RE = re.compile(
    r"Route::middleware\((.*?)\)\s*->\s*group\s*\(\s*function",
    re.IGNORECASE,
)

_GO_ROUTE_RE = re.compile(
    r"\b(?:\w+\.)?(Get|Post|Put|Delete|Patch|Route)\s*\(\s*['\"]([^'\"]+)['\"]\s*,\s*([^\n\r\)]+)",
    re.IGNORECASE,
)
_GO_HANDLE_FUNC_RE = re.compile(
    r"\b(?:mux|http)\.HandleFunc\s*\(\s*['\"]([^'\"]+)['\"]\s*,\s*([^\n\r\)]+)",
    re.IGNORECASE,
)

_LARAVEL_SCHEMA_CREATE_RE = re.compile(
    r"Schema::create\s*\(\s*['\"]([^'\"]+)['\"]",
    re.IGNORECASE,
)
_LARAVEL_COLUMN_RE = re.compile(
    r"\$table->\w+\s*\(\s*['\"]([^'\"]+)['\"]",
    re.IGNORECASE,
)

_SQL_CREATE_TABLE_RE = re.compile(
    r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?[`\"]?([a-zA-Z_][\w]*)[`\"]?\s*\((.*?)\)\s*;",
    re.IGNORECASE | re.DOTALL,
)


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("Could not read file %s: %s", path, exc)
        return ""


def _extract_middleware_from_group_args(args: str) -> list[str]:
    middleware: list[str] = []
    for match in re.finditer(r"['\"]([^'\"]+)['\"]", args):
        middleware.append(match.group(1).strip())
    return middleware


def extract_routes_laravel(repo_path: str | Path) -> list[RouteInfo]:
    root = Path(repo_path)
    routes: list[RouteInfo] = []
    route_files = [root / "routes" / "api.php", root / "routes" / "web.php"]

    for route_file in route_files:
        if not route_file.exists():
            continue

        text = _read_text(route_file)
        if not text:
            continue

        current_group_middleware: list[str] = []
        group_depth = 0

        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                continue

            middleware_match = _LARAVEL_MIDDLEWARE_GROUP_RE.search(line)
            if middleware_match:
                current_group_middleware = _extract_middleware_from_group_args(
                    middleware_match.group(1)
                )
                group_depth = 1

            route_match = _LARAVEL_ROUTE_RE.search(line)
            if route_match:
                method = route_match.group(1).upper()
                path = route_match.group(2).strip()
                handler = route_match.group(3).strip()
                routes.append(
                    RouteInfo(
                        method=method,
                        path=path,
                        handler=handler,
                        middleware=current_group_middleware.copy(),
                    )
                )

            resource_match = _LARAVEL_RESOURCE_RE.search(line)
            if resource_match:
                routes.append(
                    RouteInfo(
                        method="RESOURCE",
                        path=resource_match.group(1).strip(),
                        handler=resource_match.group(2).strip(),
                        middleware=current_group_middleware.copy(),
                    )
                )

            if group_depth > 0:
                group_depth += line.count("{")
                group_depth -= line.count("}")
                if group_depth <= 0:
                    group_depth = 0
                    current_group_middleware = []

    return routes


def _iter_go_router_files(root: Path) -> list[Path]:
    candidates: list[Path] = []
    common_paths = [
        root / "main.go",
        root / "server.go",
        root / "routes.go",
        root / "router.go",
    ]
    for path in common_paths:
        if path.exists() and path.is_file():
            candidates.append(path)

    for prefix in (root / "cmd", root / "internal"):
        if prefix.exists() and prefix.is_dir():
            candidates.extend(prefix.rglob("*.go"))

    if not candidates:
        candidates.extend(root.rglob("*.go"))

    unique_paths = {path.resolve(): path for path in candidates}
    return list(unique_paths.values())


def extract_routes_go(repo_path: str | Path) -> list[RouteInfo]:
    root = Path(repo_path)
    routes: list[RouteInfo] = []

    for go_file in _iter_go_router_files(root):
        text = _read_text(go_file)
        if not text:
            continue

        for method, path, handler in _GO_ROUTE_RE.findall(text):
            routes.append(
                RouteInfo(
                    method=method.upper(),
                    path=path.strip(),
                    handler=handler.strip(),
                )
            )

        for path, handler in _GO_HANDLE_FUNC_RE.findall(text):
            routes.append(
                RouteInfo(
                    method="HANDLEFUNC",
                    path=path.strip(),
                    handler=handler.strip(),
                )
            )

    return routes


def extract_migrations_laravel(repo_path: str | Path) -> list[MigrationInfo]:
    root = Path(repo_path)
    migrations_dir = root / "database" / "migrations"
    if not migrations_dir.exists() or not migrations_dir.is_dir():
        return []

    migrations: list[MigrationInfo] = []
    for migration_file in sorted(migrations_dir.glob("*.php")):
        text = _read_text(migration_file)
        if not text:
            continue

        table_match = _LARAVEL_SCHEMA_CREATE_RE.search(text)
        if not table_match:
            continue

        table_name = table_match.group(1)
        columns: list[str] = []
        for column_name in _LARAVEL_COLUMN_RE.findall(text):
            if column_name not in columns:
                columns.append(column_name)

        migrations.append(
            MigrationInfo(
                file_name=migration_file.name,
                table_name=table_name,
                columns=columns,
            )
        )

    return migrations


def extract_migrations_sql(repo_path: str | Path) -> list[MigrationInfo]:
    root = Path(repo_path)
    candidates: list[Path] = []

    for directory in (root / "migrations", root / "database" / "migrations"):
        if directory.exists() and directory.is_dir():
            candidates.extend(sorted(directory.glob("*.sql")))

    migrations: list[MigrationInfo] = []
    for sql_file in sorted(candidates):
        text = _read_text(sql_file)
        if not text:
            continue

        for table_name, columns_blob in _SQL_CREATE_TABLE_RE.findall(text):
            columns: list[str] = []
            for raw_line in columns_blob.splitlines():
                line = raw_line.strip().rstrip(",")
                if not line:
                    continue
                upper = line.upper()
                if upper.startswith(
                    ("PRIMARY KEY", "FOREIGN KEY", "UNIQUE", "CONSTRAINT", "INDEX")
                ):
                    continue
                columns.append(line)

            migrations.append(
                MigrationInfo(
                    file_name=sql_file.name,
                    table_name=table_name,
                    columns=columns,
                )
            )

    return migrations


def extract_env(repo_path: str | Path) -> list[EnvVar]:
    root = Path(repo_path)
    env_file = root / ".env.example"
    if not env_file.exists() or not env_file.is_file():
        return []

    text = _read_text(env_file)
    if not text:
        return []

    env_vars: list[EnvVar] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue

        key, value_part = line.split("=", 1)
        key = key.strip()
        value_part = value_part.strip()

        comment = ""
        default = value_part
        if "#" in value_part:
            default_part, comment_part = value_part.split("#", 1)
            default = default_part.strip()
            comment = comment_part.strip()

        env_vars.append(EnvVar(name=key, default=default, comment=comment))

    return env_vars


def _normalize_environment(raw_environment: Any) -> list[str]:
    if isinstance(raw_environment, dict):
        return [f"{key}={value}" for key, value in raw_environment.items()]
    if isinstance(raw_environment, list):
        return [str(item) for item in raw_environment]
    return []


def _normalize_depends_on(raw_depends_on: Any) -> list[str]:
    if isinstance(raw_depends_on, dict):
        return [str(name) for name in raw_depends_on]
    if isinstance(raw_depends_on, list):
        return [str(item) for item in raw_depends_on]
    return []


def extract_docker(repo_path: str | Path) -> DockerComposeInfo:
    root = Path(repo_path)
    filenames = [
        "docker-compose.yml",
        "docker-compose.yaml",
        "compose.yml",
        "compose.yaml",
    ]

    compose_file: Path | None = None
    for filename in filenames:
        candidate = root / filename
        if candidate.exists() and candidate.is_file():
            compose_file = candidate
            break

    if compose_file is None:
        return DockerComposeInfo()

    try:
        data = yaml.safe_load(_read_text(compose_file)) or {}
    except yaml.YAMLError as exc:
        logger.warning("Could not parse docker compose file %s: %s", compose_file, exc)
        return DockerComposeInfo()

    services_data = data.get("services", {}) if isinstance(data, dict) else {}
    if not isinstance(services_data, dict):
        return DockerComposeInfo()

    services: list[DockerService] = []
    for service_name, service_config in services_data.items():
        if not isinstance(service_config, dict):
            continue

        ports = [str(port) for port in service_config.get("ports", [])]
        environment = _normalize_environment(service_config.get("environment"))
        depends_on = _normalize_depends_on(service_config.get("depends_on"))

        services.append(
            DockerService(
                name=str(service_name),
                image=str(service_config.get("image", "")),
                ports=ports,
                environment=environment,
                depends_on=depends_on,
            )
        )

    return DockerComposeInfo(services=services)


def extract_structured(repo_path: str | Path, stack: str) -> dict[str, Any]:
    routes: list[RouteInfo] = []
    migrations: list[MigrationInfo] = []

    if stack == "laravel":
        routes = extract_routes_laravel(repo_path)
        migrations = extract_migrations_laravel(repo_path)
    elif stack in {"go", "go-chi"}:
        routes = extract_routes_go(repo_path)
        migrations = extract_migrations_sql(repo_path)

    env_vars = extract_env(repo_path)
    docker_info = extract_docker(repo_path)

    return {
        "routes": [asdict(route) for route in routes],
        "migrations": [asdict(migration) for migration in migrations],
        "env": [asdict(item) for item in env_vars],
        "docker": asdict(docker_info),
    }
