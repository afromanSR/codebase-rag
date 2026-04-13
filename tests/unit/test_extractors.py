from __future__ import annotations

import textwrap
from pathlib import Path

from codebase_rag.indexer.extractors import (
    DockerComposeInfo,
    extract_docker,
    extract_env,
    extract_migrations_laravel,
    extract_migrations_sql,
    extract_routes_go,
    extract_routes_laravel,
    extract_structured,
)


def test_extract_routes_laravel(tmp_path: Path) -> None:
    routes_dir = tmp_path / "routes"
    routes_dir.mkdir(parents=True)
    (routes_dir / "api.php").write_text(
        """<?php
Route::get('/users', [UserController::class, 'index']);
Route::post('/users', [UserController::class, 'store']);
Route::put('/users/{id}', [UserController::class, 'update']);
Route::delete('/users/{id}', [UserController::class, 'destroy']);
""",
        encoding="utf-8",
    )

    routes = extract_routes_laravel(tmp_path)

    assert len(routes) == 4
    assert [route.method for route in routes] == ["GET", "POST", "PUT", "DELETE"]
    assert [route.path for route in routes] == [
        "/users",
        "/users",
        "/users/{id}",
        "/users/{id}",
    ]


def test_extract_routes_laravel_resource(tmp_path: Path) -> None:
    routes_dir = tmp_path / "routes"
    routes_dir.mkdir(parents=True)
    (routes_dir / "api.php").write_text(
        """<?php
Route::resource('/posts', PostController::class);
""",
        encoding="utf-8",
    )

    routes = extract_routes_laravel(tmp_path)

    assert len(routes) == 1
    assert routes[0].method == "RESOURCE"
    assert routes[0].path == "/posts"
    assert "PostController" in routes[0].handler


def test_extract_routes_go(tmp_path: Path) -> None:
    (tmp_path / "main.go").write_text(
        """package main

func setupRoutes(r Router) {
	r.Get("/api/users", handlers.ListUsers)
	r.Post("/api/users", handlers.CreateUser)
	r.Delete("/api/users/{id}", handlers.DeleteUser)
}
""",
        encoding="utf-8",
    )

    routes = extract_routes_go(tmp_path)

    assert len(routes) == 3
    assert [route.method for route in routes] == ["GET", "POST", "DELETE"]
    assert [route.path for route in routes] == [
        "/api/users",
        "/api/users",
        "/api/users/{id}",
    ]


def test_extract_migrations_laravel(tmp_path: Path) -> None:
    migrations_dir = tmp_path / "database" / "migrations"
    migrations_dir.mkdir(parents=True)
    (migrations_dir / "2024_01_01_create_users_table.php").write_text(
        """<?php
Schema::create('users', function (Blueprint $table) {
	$table->id();
	$table->string('name');
	$table->string('email');
	$table->timestamps();
});
""",
        encoding="utf-8",
    )

    migrations = extract_migrations_laravel(tmp_path)

    assert len(migrations) == 1
    assert migrations[0].table_name == "users"
    assert "name" in migrations[0].columns
    assert "email" in migrations[0].columns


def test_extract_migrations_sql(tmp_path: Path) -> None:
    migrations_dir = tmp_path / "migrations"
    migrations_dir.mkdir(parents=True)
    (migrations_dir / "001_create_users.sql").write_text(
        """CREATE TABLE users (
	id SERIAL PRIMARY KEY,
	name VARCHAR(255),
	email VARCHAR(255)
);
""",
        encoding="utf-8",
    )

    migrations = extract_migrations_sql(tmp_path)

    assert len(migrations) == 1
    assert migrations[0].table_name == "users"


def test_extract_env(tmp_path: Path) -> None:
    (tmp_path / ".env.example").write_text(
        """APP_NAME=MyApp
APP_ENV=local
DB_HOST=127.0.0.1
DB_PASSWORD=  # Leave empty
# This is a comment
REDIS_HOST=127.0.0.1
""",
        encoding="utf-8",
    )

    env_vars = extract_env(tmp_path)

    assert len(env_vars) == 5
    assert env_vars[0].name == "APP_NAME"
    assert env_vars[0].default == "MyApp"
    assert env_vars[0].comment == ""
    assert env_vars[3].name == "DB_PASSWORD"
    assert env_vars[3].default == ""
    assert env_vars[3].comment == "Leave empty"


def test_extract_env_missing_file(tmp_path: Path) -> None:
    env_vars = extract_env(tmp_path)
    assert env_vars == []


def test_extract_docker(tmp_path: Path) -> None:
    (tmp_path / "docker-compose.yml").write_text(
        textwrap.dedent(
            """\
			version: "3.8"
			services:
			  app:
			    image: php:8.2
			    ports:
			      - "8080:80"
			    depends_on:
			      - db
			  db:
			    image: mysql:8.0
			    ports:
			      - "3306:3306"
			    environment:
			      - MYSQL_ROOT_PASSWORD=secret
			"""
        ),
        encoding="utf-8",
    )

    docker_info = extract_docker(tmp_path)

    assert len(docker_info.services) == 2
    by_name = {service.name: service for service in docker_info.services}
    assert by_name["app"].image == "php:8.2"
    assert by_name["app"].ports == ["8080:80"]
    assert by_name["app"].depends_on == ["db"]
    assert by_name["db"].image == "mysql:8.0"
    assert by_name["db"].ports == ["3306:3306"]


def test_extract_docker_missing_file(tmp_path: Path) -> None:
    docker_info = extract_docker(tmp_path)
    assert isinstance(docker_info, DockerComposeInfo)
    assert docker_info.services == []


def test_extract_structured_laravel(tmp_path: Path) -> None:
    routes_dir = tmp_path / "routes"
    routes_dir.mkdir(parents=True)
    (routes_dir / "api.php").write_text(
        "Route::get('/users', [UserController::class, 'index']);\n",
        encoding="utf-8",
    )

    migrations_dir = tmp_path / "database" / "migrations"
    migrations_dir.mkdir(parents=True)
    (migrations_dir / "2024_01_01_create_users_table.php").write_text(
        """Schema::create('users', function (Blueprint $table) {
	$table->string('name');
});
""",
        encoding="utf-8",
    )

    (tmp_path / ".env.example").write_text("APP_ENV=local\n", encoding="utf-8")
    (tmp_path / "docker-compose.yml").write_text(
        textwrap.dedent(
            """\
			services:
			  app:
			    image: php:8.2
			"""
        ),
        encoding="utf-8",
    )

    structured = extract_structured(tmp_path, stack="laravel")

    assert set(structured.keys()) == {"routes", "migrations", "env", "docker"}
    assert len(structured["routes"]) == 1
    assert len(structured["migrations"]) == 1
    assert len(structured["env"]) == 1
    assert len(structured["docker"]["services"]) == 1


def test_extract_structured_unknown(tmp_path: Path) -> None:
    (tmp_path / ".env.example").write_text("APP_ENV=local\n", encoding="utf-8")
    (tmp_path / "docker-compose.yml").write_text(
        textwrap.dedent(
            """\
			services:
			  app:
			    image: php:8.2
			"""
        ),
        encoding="utf-8",
    )

    structured = extract_structured(tmp_path, stack="unknown")

    assert set(structured.keys()) == {"routes", "migrations", "env", "docker"}
    assert structured["routes"] == []
    assert structured["migrations"] == []
    assert len(structured["env"]) == 1
    assert len(structured["docker"]["services"]) == 1
