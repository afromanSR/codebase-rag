from __future__ import annotations

from pathlib import Path

import pytest

from codebase_rag.indexer.chunkers import (
    Chunk,
    _estimate_tokens,
    chunk_fallback,
    chunk_file,
    chunk_go,
    chunk_markdown,
    chunk_php,
    chunk_typescript,
    chunk_vue,
    chunk_yaml,
    get_chunker,
)


def test_php_chunker_splits_class_by_methods(tmp_path: Path) -> None:
    content = """<?php
namespace App\\Models;

class User {
	public function one(): string {
		return \"one\";
	}

	public function two(): string {
		return \"two\";
	}

	public function three(): string {
		return \"three\";
	}
}
"""
    file_path = tmp_path / "User.php"
    file_path.write_text(content, encoding="utf-8")

    chunks = chunk_php(file_path, content, "repo", tmp_path, max_tokens=8)

    assert len(chunks) == 3
    assert all(chunk.chunk_type == "method" for chunk in chunks)
    assert [chunk.symbol_name for chunk in chunks] == [
        "User.one",
        "User.two",
        "User.three",
    ]


def test_php_chunker_whole_class_when_small(tmp_path: Path) -> None:
    content = """<?php
class User {
	public function getName(): string { return $this->name; }
}
"""
    file_path = tmp_path / "User.php"
    file_path.write_text(content, encoding="utf-8")

    chunks = chunk_php(file_path, content, "repo", tmp_path, max_tokens=512)

    assert len(chunks) == 1
    assert chunks[0].chunk_type == "class"
    assert chunks[0].symbol_name == "User"


def test_php_chunker_standalone_function(tmp_path: Path) -> None:
    content = """<?php
function greet(): string {
	return "hi";
}
"""
    file_path = tmp_path / "helpers.php"
    file_path.write_text(content, encoding="utf-8")

    chunks = chunk_php(file_path, content, "repo", tmp_path, max_tokens=512)

    assert len(chunks) == 1
    assert chunks[0].chunk_type == "function"
    assert chunks[0].symbol_name == "greet"


def test_go_chunker_splits_functions(tmp_path: Path) -> None:
    content = """package main

func Hello() string {
	return "hello"
}

func World() string {
	return "world"
}
"""
    file_path = tmp_path / "main.go"
    file_path.write_text(content, encoding="utf-8")

    chunks = chunk_go(file_path, content, "repo", tmp_path, max_tokens=512)

    function_chunks = [chunk for chunk in chunks if chunk.chunk_type == "function"]
    assert len(function_chunks) == 2
    assert function_chunks[0].symbol_name == "main.Hello"
    assert function_chunks[1].symbol_name == "main.World"


def test_go_chunker_struct(tmp_path: Path) -> None:
    content = """package main

type User struct {
	Name string
}
"""
    file_path = tmp_path / "user.go"
    file_path.write_text(content, encoding="utf-8")

    chunks = chunk_go(file_path, content, "repo", tmp_path, max_tokens=512)

    assert len(chunks) == 1
    assert chunks[0].chunk_type == "struct"
    assert chunks[0].symbol_name == "main.User"


def test_typescript_chunker_exports(tmp_path: Path) -> None:
    content = """export function add(a: number, b: number): number {
	return a + b;
}

export const PI = 3.14;
"""
    file_path = tmp_path / "math.ts"
    file_path.write_text(content, encoding="utf-8")

    chunks = chunk_typescript(file_path, content, "repo", tmp_path, max_tokens=512)

    assert len(chunks) == 2
    assert chunks[0].chunk_type == "function"
    assert chunks[1].chunk_type == "const"
    assert chunks[0].symbol_name == "add"
    assert chunks[1].symbol_name == "PI"


def test_vue_chunker_splits_blocks(tmp_path: Path) -> None:
    content = """<template>
  <div>Hello</div>
</template>

<script setup lang="ts">
const msg = "hello"
</script>

<style scoped>
.hello { color: red; }
</style>
"""
    file_path = tmp_path / "App.vue"
    file_path.write_text(content, encoding="utf-8")

    chunks = chunk_vue(file_path, content, "repo", tmp_path, max_tokens=512)

    assert len(chunks) == 3
    assert [chunk.chunk_type for chunk in chunks] == ["template", "script", "style"]


def test_markdown_chunker_splits_headers(tmp_path: Path) -> None:
    content = """# Title

Intro text

## Section 1

Content 1

## Section 2

Content 2
"""
    file_path = tmp_path / "README.md"
    file_path.write_text(content, encoding="utf-8")

    chunks = chunk_markdown(file_path, content, "repo", tmp_path, max_tokens=512)

    assert len(chunks) == 3
    assert all(chunk.chunk_type == "section" for chunk in chunks)


def test_markdown_chunker_symbol_name(tmp_path: Path) -> None:
    content = """# Title

Intro text

## Section 1

Content 1
"""
    file_path = tmp_path / "notes.md"
    file_path.write_text(content, encoding="utf-8")

    chunks = chunk_markdown(file_path, content, "repo", tmp_path, max_tokens=512)

    assert chunks[0].symbol_name == "Title"
    assert chunks[1].symbol_name == "Section 1"


def test_yaml_chunker_top_level_keys(tmp_path: Path) -> None:
    content = """version: '3.9'
services:
  web:
	image: nginx
database:
  host: localhost
"""
    file_path = tmp_path / "config.yaml"
    file_path.write_text(content, encoding="utf-8")

    chunks = chunk_yaml(file_path, content, "repo", tmp_path, max_tokens=512)

    assert len(chunks) == 3
    assert [chunk.symbol_name for chunk in chunks] == [
        "version",
        "services",
        "database",
    ]


def test_fallback_chunker_sliding_window(tmp_path: Path) -> None:
    file_path = tmp_path / "long.txt"
    lines = [f"line {i:03d} with some content\n" for i in range(1, 61)]
    content = "".join(lines)
    file_path.write_text(content, encoding="utf-8")

    chunks = chunk_fallback(file_path, content, "repo", tmp_path, max_tokens=20, overlap_tokens=8)

    assert len(chunks) > 1
    for chunk in chunks:
        assert _estimate_tokens(chunk.text) <= 24
    assert chunks[1].start_line <= chunks[0].end_line


def test_chunk_metadata_populated(tmp_path: Path) -> None:
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    file_path = repo_path / "docs" / "README.md"
    file_path.parent.mkdir(parents=True)
    content = """# Title

Content
"""
    file_path.write_text(content, encoding="utf-8")

    chunks = chunk_markdown(file_path, content, "my-repo", repo_path, max_tokens=512)

    assert len(chunks) == 1
    chunk = chunks[0]
    assert isinstance(chunk, Chunk)
    assert chunk.id == "my-repo:docs/README.md:1"
    assert chunk.repo_name == "my-repo"
    assert chunk.file_path == "docs/README.md"
    assert chunk.start_line == 1
    assert chunk.end_line >= chunk.start_line


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("file.php", chunk_php),
        ("file.go", chunk_go),
        ("file.ts", chunk_typescript),
        ("file.tsx", chunk_typescript),
        ("file.vue", chunk_vue),
        ("file.md", chunk_markdown),
        ("file.yaml", chunk_yaml),
        ("file.yml", chunk_yaml),
    ],
)
def test_get_chunker_returns_correct_type(tmp_path: Path, filename: str, expected: object) -> None:
    chunker = get_chunker(tmp_path / filename, "repo", tmp_path)
    assert chunker == expected


def test_chunk_file_reads_and_chunks(tmp_path: Path) -> None:
    repo_path = tmp_path / "workspace"
    repo_path.mkdir()
    file_path = repo_path / "math.ts"
    file_path.write_text(
        """export function add(a: number, b: number): number {
	return a + b;
}
""",
        encoding="utf-8",
    )

    chunks = chunk_file(file_path=file_path, repo_name="repo", repo_path=repo_path, max_tokens=512)

    assert len(chunks) == 1
    assert chunks[0].chunk_type == "function"
    assert chunks[0].file_mtime > 0


def test_estimate_tokens() -> None:
    text = "hello world"
    assert _estimate_tokens(text) == len(text) // 4
