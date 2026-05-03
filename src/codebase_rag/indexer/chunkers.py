from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class Chunk:
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


ChunkerFn = Callable[[Path, str, str, Path, int], list[Chunk]]

_LANGUAGE_BY_SUFFIX: dict[str, str] = {
    ".php": "php",
    ".go": "go",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".vue": "vue",
    ".md": "markdown",
    ".yaml": "yaml",
    ".yml": "yaml",
}


def _estimate_tokens(text: str) -> int:
    return len(text) // 4


def _split_text_by_tokens(text: str, max_tokens: int) -> list[str]:
    """Split text into pieces under max_tokens, respecting line boundaries when possible."""
    if _estimate_tokens(text) <= max_tokens:
        return [text]

    max_chars = max(max_tokens * 4, 1)
    pieces: list[str] = []
    lines = text.splitlines(keepends=True) or [text]
    buf = ""
    buf_tokens = 0

    def _flush() -> None:
        nonlocal buf, buf_tokens
        if buf:
            pieces.append(buf)
            buf = ""
            buf_tokens = 0

    for line in lines:
        line_tokens = _estimate_tokens(line) or 1
        if line_tokens > max_tokens:
            _flush()
            for start in range(0, len(line), max_chars):
                pieces.append(line[start : start + max_chars])
            continue
        if buf_tokens + line_tokens > max_tokens and buf:
            _flush()
        buf += line
        buf_tokens += line_tokens
    _flush()
    return pieces or [text]


def _enforce_max_tokens(chunks: list[Chunk], max_tokens: int) -> list[Chunk]:
    """Split any chunk whose estimated tokens exceed max_tokens into sub-chunks."""
    if max_tokens <= 0:
        return chunks
    result: list[Chunk] = []
    for chunk in chunks:
        if _estimate_tokens(chunk.text) <= max_tokens:
            result.append(chunk)
            continue
        pieces = _split_text_by_tokens(chunk.text, max_tokens)
        line_span = max(chunk.end_line - chunk.start_line + 1, 1)
        per_piece = max(line_span // max(len(pieces), 1), 1)
        for i, piece_text in enumerate(pieces):
            sub_start = chunk.start_line + i * per_piece
            sub_end = (
                chunk.start_line + (i + 1) * per_piece - 1
                if i < len(pieces) - 1
                else chunk.end_line
            )
            sub_id = f"{chunk.id}#part{i}" if i > 0 else chunk.id
            result.append(
                Chunk(
                    id=sub_id,
                    text=piece_text,
                    repo_name=chunk.repo_name,
                    file_path=chunk.file_path,
                    abs_file_path=chunk.abs_file_path,
                    start_line=sub_start,
                    end_line=max(sub_end, sub_start),
                    language=chunk.language,
                    chunk_type=chunk.chunk_type,
                    symbol_name=chunk.symbol_name,
                    file_mtime=chunk.file_mtime,
                )
            )
    return result


def _language_for_file(file_path: Path) -> str:
    return _LANGUAGE_BY_SUFFIX.get(file_path.suffix.lower(), "text")


def _relative_file_path(file_path: Path, repo_path: Path) -> str:
    try:
        return str(file_path.resolve().relative_to(repo_path.resolve()))
    except ValueError:
        return file_path.name


def _line_number_at_offset(content: str, offset: int) -> int:
    return content.count("\n", 0, max(offset, 0)) + 1


def _find_block_end(content: str, start_offset: int) -> int:
    open_brace = content.find("{", start_offset)
    if open_brace == -1:
        return len(content)

    depth = 0
    for index in range(open_brace, len(content)):
        char = content[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return index + 1
    return len(content)


def _make_chunk(
    *,
    file_path: Path,
    repo_name: str,
    repo_path: Path,
    content: str,
    start_offset: int,
    end_offset: int,
    chunk_type: str,
    symbol_name: str | None,
    language: str | None = None,
) -> Chunk:
    start_line = _line_number_at_offset(content, start_offset)
    end_line = _line_number_at_offset(content, max(end_offset - 1, start_offset))
    relative_path = _relative_file_path(file_path, repo_path)
    lang = language or _language_for_file(file_path)

    return Chunk(
        id=f"{repo_name}:{relative_path}:{start_line}",
        text=content[start_offset:end_offset],
        repo_name=repo_name,
        file_path=relative_path,
        abs_file_path=str(file_path.resolve()),
        start_line=start_line,
        end_line=end_line,
        language=lang,
        chunk_type=chunk_type,
        symbol_name=symbol_name,
        file_mtime=0.0,
    )


def get_chunker(
    file_path: str | Path,
    repo_name: str,
    repo_path: str | Path,
    max_tokens: int = 512,
    overlap_tokens: int = 64,
) -> ChunkerFn:
    del repo_name, repo_path, max_tokens
    path = Path(file_path)
    suffix = path.suffix.lower()

    mapping: dict[str, ChunkerFn] = {
        ".php": chunk_php,
        ".go": chunk_go,
        ".ts": chunk_typescript,
        ".tsx": chunk_typescript,
        ".vue": chunk_vue,
        ".md": chunk_markdown,
        ".yaml": chunk_yaml,
        ".yml": chunk_yaml,
    }
    if suffix in mapping:
        return mapping[suffix]

    def _fallback(
        file_path: Path, content: str, repo_name: str, repo_path: Path, max_tokens: int
    ) -> list[Chunk]:
        return chunk_fallback(
            file_path=file_path,
            content=content,
            repo_name=repo_name,
            repo_path=repo_path,
            max_tokens=max_tokens,
            overlap_tokens=overlap_tokens,
        )

    return _fallback


def chunk_php(
    file_path: Path, content: str, repo_name: str, repo_path: Path, max_tokens: int
) -> list[Chunk]:
    class_pattern = re.compile(
        r"^\s*(?:final\s+|abstract\s+)?class\s+([A-Za-z_][A-Za-z0-9_]*)\b", re.MULTILINE
    )
    method_pattern = re.compile(
        r"^\s*(?:public|protected|private|static|final|abstract|\s)*function\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(",
        re.MULTILINE,
    )
    function_pattern = re.compile(r"^\s*function\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(", re.MULTILINE)
    namespace_match = re.search(r"^\s*namespace\s+([^;]+);", content, re.MULTILINE)
    namespace_name = namespace_match.group(1).strip() if namespace_match else None

    chunks: list[Chunk] = []
    class_spans: list[tuple[int, int]] = []

    for class_match in class_pattern.finditer(content):
        class_name = class_match.group(1)
        class_start = class_match.start()
        class_end = _find_block_end(content, class_match.end())
        class_spans.append((class_start, class_end))
        class_text = content[class_start:class_end]

        if _estimate_tokens(class_text) <= max_tokens:
            symbol = f"{namespace_name}\\{class_name}" if namespace_name else class_name
            chunks.append(
                _make_chunk(
                    file_path=file_path,
                    repo_name=repo_name,
                    repo_path=repo_path,
                    content=content,
                    start_offset=class_start,
                    end_offset=class_end,
                    chunk_type="class",
                    symbol_name=symbol,
                    language="php",
                )
            )
            continue

        method_matches = list(method_pattern.finditer(class_text))
        if not method_matches:
            fallback_chunks = chunk_fallback(
                file_path=file_path,
                content=class_text,
                repo_name=repo_name,
                repo_path=repo_path,
                max_tokens=max_tokens,
            )
            for fallback_chunk in fallback_chunks:
                fallback_chunk.start_line += _line_number_at_offset(content, class_start) - 1
                fallback_chunk.end_line += _line_number_at_offset(content, class_start) - 1
                fallback_chunk.id = (
                    f"{repo_name}:{fallback_chunk.file_path}:{fallback_chunk.start_line}"
                )
                fallback_chunk.language = "php"
                chunks.append(fallback_chunk)
            continue

        for index, method_match in enumerate(method_matches):
            method_name = method_match.group(1)
            method_start = class_start + method_match.start()
            method_end = (
                class_start + method_matches[index + 1].start()
                if index + 1 < len(method_matches)
                else class_end
            )
            symbol = f"{class_name}.{method_name}"
            chunks.append(
                _make_chunk(
                    file_path=file_path,
                    repo_name=repo_name,
                    repo_path=repo_path,
                    content=content,
                    start_offset=method_start,
                    end_offset=method_end,
                    chunk_type="method",
                    symbol_name=symbol,
                    language="php",
                )
            )

    def _inside_class(offset: int) -> bool:
        return any(start <= offset < end for start, end in class_spans)

    for function_match in function_pattern.finditer(content):
        if _inside_class(function_match.start()):
            continue
        func_name = function_match.group(1)
        func_start = function_match.start()
        func_end = _find_block_end(content, function_match.end())
        symbol = f"{namespace_name}\\{func_name}" if namespace_name else func_name
        chunks.append(
            _make_chunk(
                file_path=file_path,
                repo_name=repo_name,
                repo_path=repo_path,
                content=content,
                start_offset=func_start,
                end_offset=func_end,
                chunk_type="function",
                symbol_name=symbol,
                language="php",
            )
        )

    if not chunks:
        return chunk_fallback(file_path, content, repo_name, repo_path, max_tokens)

    chunks.sort(key=lambda chunk: chunk.start_line)
    return chunks


def chunk_go(
    file_path: Path, content: str, repo_name: str, repo_path: Path, max_tokens: int
) -> list[Chunk]:
    func_pattern = re.compile(
        r"^\s*func\s*(\([^)]+\)\s*)?([A-Za-z_][A-Za-z0-9_]*)\s*\(", re.MULTILINE
    )
    struct_pattern = re.compile(r"^\s*type\s+([A-Za-z_][A-Za-z0-9_]*)\s+struct\b", re.MULTILINE)
    package_match = re.search(r"^\s*package\s+([A-Za-z_][A-Za-z0-9_]*)\b", content, re.MULTILINE)
    package_name = package_match.group(1) if package_match else None

    chunks: list[Chunk] = []

    for struct_match in struct_pattern.finditer(content):
        struct_name = struct_match.group(1)
        start_offset = struct_match.start()
        end_offset = _find_block_end(content, struct_match.end())
        symbol = f"{package_name}.{struct_name}" if package_name else struct_name
        chunks.append(
            _make_chunk(
                file_path=file_path,
                repo_name=repo_name,
                repo_path=repo_path,
                content=content,
                start_offset=start_offset,
                end_offset=end_offset,
                chunk_type="struct",
                symbol_name=symbol,
                language="go",
            )
        )

    for func_match in func_pattern.finditer(content):
        receiver = func_match.group(1) or ""
        func_name = func_match.group(2)
        start_offset = func_match.start()
        end_offset = _find_block_end(content, func_match.end())
        receiver_name_match = re.search(r"\*?([A-Za-z_][A-Za-z0-9_]*)", receiver)
        receiver_name = receiver_name_match.group(1) if receiver_name_match else None
        if receiver_name:
            symbol = f"{receiver_name}.{func_name}"
        elif package_name:
            symbol = f"{package_name}.{func_name}"
        else:
            symbol = func_name
        chunks.append(
            _make_chunk(
                file_path=file_path,
                repo_name=repo_name,
                repo_path=repo_path,
                content=content,
                start_offset=start_offset,
                end_offset=end_offset,
                chunk_type="function",
                symbol_name=symbol,
                language="go",
            )
        )

    if not chunks:
        return chunk_fallback(file_path, content, repo_name, repo_path, max_tokens)

    chunks.sort(key=lambda chunk: chunk.start_line)
    return chunks


def chunk_typescript(
    file_path: Path, content: str, repo_name: str, repo_path: Path, max_tokens: int
) -> list[Chunk]:
    export_pattern = re.compile(
        r"^[ \t]*export\s+(?:default\s+)?(?:async\s+)?(?:function|class|const)\b",
        re.MULTILINE,
    )
    matches = list(export_pattern.finditer(content))
    if not matches:
        return chunk_fallback(file_path, content, repo_name, repo_path, max_tokens)

    chunks: list[Chunk] = []
    for index, match in enumerate(matches):
        start_offset = match.start()
        end_offset = matches[index + 1].start() if index + 1 < len(matches) else len(content)
        line_end = content.find("\n", start_offset)
        first_line = content[start_offset : (line_end if line_end != -1 else len(content))]
        if re.search(r"\bfunction\b", first_line):
            chunk_type = "function"
        elif re.search(r"\bclass\b", first_line):
            chunk_type = "class"
        else:
            chunk_type = "const"

        symbol_match = re.search(
            r"\b(?:function|class|const)\s+([A-Za-z_][A-Za-z0-9_]*)",
            first_line,
        )
        symbol_name = symbol_match.group(1) if symbol_match else None
        chunks.append(
            _make_chunk(
                file_path=file_path,
                repo_name=repo_name,
                repo_path=repo_path,
                content=content,
                start_offset=start_offset,
                end_offset=end_offset,
                chunk_type=chunk_type,
                symbol_name=symbol_name,
                language="typescript",
            )
        )

    return chunks


def chunk_vue(
    file_path: Path, content: str, repo_name: str, repo_path: Path, max_tokens: int
) -> list[Chunk]:
    blocks: list[tuple[str, int, int]] = []
    for block_name in ("template", "script", "style"):
        pattern = re.compile(rf"<{block_name}\b[^>]*>.*?</{block_name}>", re.DOTALL)
        for match in pattern.finditer(content):
            blocks.append((block_name, match.start(), match.end()))

    if not blocks:
        return chunk_fallback(file_path, content, repo_name, repo_path, max_tokens)

    blocks.sort(key=lambda block: block[1])
    chunks: list[Chunk] = []

    for block_type, start_offset, end_offset in blocks:
        block_text = content[start_offset:end_offset]
        if _estimate_tokens(block_text) <= max_tokens:
            chunks.append(
                _make_chunk(
                    file_path=file_path,
                    repo_name=repo_name,
                    repo_path=repo_path,
                    content=content,
                    start_offset=start_offset,
                    end_offset=end_offset,
                    chunk_type=block_type,
                    symbol_name=block_type,
                    language="vue",
                )
            )
            continue

        block_start_line = _line_number_at_offset(content, start_offset)
        fallback_chunks = chunk_fallback(
            file_path=file_path,
            content=block_text,
            repo_name=repo_name,
            repo_path=repo_path,
            max_tokens=max_tokens,
        )
        for fallback_chunk in fallback_chunks:
            fallback_chunk.start_line += block_start_line - 1
            fallback_chunk.end_line += block_start_line - 1
            fallback_chunk.id = (
                f"{repo_name}:{fallback_chunk.file_path}:{fallback_chunk.start_line}"
            )
            fallback_chunk.language = "vue"
            fallback_chunk.chunk_type = block_type
            fallback_chunk.symbol_name = block_type
            chunks.append(fallback_chunk)

    return chunks


def chunk_markdown(
    file_path: Path, content: str, repo_name: str, repo_path: Path, max_tokens: int
) -> list[Chunk]:
    header_pattern = re.compile(r"^(#{1,3})\s+(.+)$", re.MULTILINE)
    headers = [
        (match.start(), len(match.group(1)), match.group(2).strip())
        for match in header_pattern.finditer(content)
    ]
    if not headers:
        return chunk_fallback(file_path, content, repo_name, repo_path, max_tokens)

    chunks: list[Chunk] = []
    for index, (start_offset, level, title) in enumerate(headers):
        end_offset = len(content)
        for next_offset, next_level, _ in headers[index + 1 :]:
            if next_level <= level:
                end_offset = next_offset
                break
        chunks.append(
            _make_chunk(
                file_path=file_path,
                repo_name=repo_name,
                repo_path=repo_path,
                content=content,
                start_offset=start_offset,
                end_offset=end_offset,
                chunk_type="section",
                symbol_name=title,
                language="markdown",
            )
        )

    return chunks


def chunk_yaml(
    file_path: Path, content: str, repo_name: str, repo_path: Path, max_tokens: int
) -> list[Chunk]:
    top_level_pattern = re.compile(r"^([A-Za-z0-9_.-][^:\n]*)\s*:", re.MULTILINE)
    top_level_matches = list(top_level_pattern.finditer(content))
    if not top_level_matches:
        return chunk_fallback(file_path, content, repo_name, repo_path, max_tokens)

    chunks: list[Chunk] = []
    is_docker_compose = "docker-compose" in file_path.name

    if is_docker_compose:
        services_match = next(
            (match for match in top_level_matches if match.group(1).strip() == "services"),
            None,
        )
        if services_match:
            services_start = services_match.start()
            next_top = [m.start() for m in top_level_matches if m.start() > services_start]
            services_end = min(next_top) if next_top else len(content)
            services_text = content[services_start:services_end]
            service_pattern = re.compile(r"^\s{2}([A-Za-z0-9_.-]+)\s*:\s*$", re.MULTILINE)
            service_matches = list(service_pattern.finditer(services_text))

            for index, service_match in enumerate(service_matches):
                start_offset = services_start + service_match.start()
                end_offset = (
                    services_start + service_matches[index + 1].start()
                    if index + 1 < len(service_matches)
                    else services_end
                )
                service_name = service_match.group(1)
                chunks.append(
                    _make_chunk(
                        file_path=file_path,
                        repo_name=repo_name,
                        repo_path=repo_path,
                        content=content,
                        start_offset=start_offset,
                        end_offset=end_offset,
                        chunk_type="config",
                        symbol_name=service_name,
                        language="yaml",
                    )
                )

    if not chunks:
        for index, match in enumerate(top_level_matches):
            start_offset = match.start()
            end_offset = (
                top_level_matches[index + 1].start()
                if index + 1 < len(top_level_matches)
                else len(content)
            )
            key_name = match.group(1).strip()
            chunks.append(
                _make_chunk(
                    file_path=file_path,
                    repo_name=repo_name,
                    repo_path=repo_path,
                    content=content,
                    start_offset=start_offset,
                    end_offset=end_offset,
                    chunk_type="config",
                    symbol_name=key_name,
                    language="yaml",
                )
            )

    return chunks


def chunk_fallback(
    file_path: Path,
    content: str,
    repo_name: str,
    repo_path: Path,
    max_tokens: int,
    overlap_tokens: int = 64,
) -> list[Chunk]:
    if not content:
        return []

    lines = content.splitlines(keepends=True)
    if not lines:
        return []

    line_tokens = [_estimate_tokens(line) or 1 for line in lines]
    chunks: list[Chunk] = []
    start_index = 0

    while start_index < len(lines):
        token_total = 0
        end_index = start_index
        while end_index < len(lines):
            next_tokens = line_tokens[end_index]
            if token_total + next_tokens > max_tokens and end_index > start_index:
                break
            token_total += next_tokens
            end_index += 1

        chunk_text = "".join(lines[start_index:end_index])
        start_line = start_index + 1
        end_line = end_index
        relative_path = _relative_file_path(file_path, repo_path)
        chunks.append(
            Chunk(
                id=f"{repo_name}:{relative_path}:{start_line}",
                text=chunk_text,
                repo_name=repo_name,
                file_path=relative_path,
                abs_file_path=str(file_path.resolve()),
                start_line=start_line,
                end_line=end_line,
                language=_language_for_file(file_path),
                chunk_type="text",
                symbol_name=None,
                file_mtime=0.0,
            )
        )

        if end_index >= len(lines):
            break

        overlap_total = 0
        overlap_start = end_index
        while overlap_start > start_index:
            candidate = overlap_start - 1
            overlap_total += line_tokens[candidate]
            if overlap_total >= overlap_tokens:
                overlap_start = candidate
                break
            overlap_start = candidate

        start_index = overlap_start if overlap_start > start_index else end_index

    return chunks


def chunk_file(
    file_path: str | Path,
    repo_name: str,
    repo_path: str | Path,
    max_tokens: int = 512,
    overlap_tokens: int = 64,
) -> list[Chunk]:
    path = Path(file_path).resolve()
    repo_root = Path(repo_path).resolve()
    content = path.read_text(encoding="utf-8", errors="ignore")
    file_mtime = path.stat().st_mtime
    chunker = get_chunker(
        file_path=path,
        repo_name=repo_name,
        repo_path=repo_root,
        max_tokens=max_tokens,
        overlap_tokens=overlap_tokens,
    )
    chunks = chunker(path, content, repo_name, repo_root, max_tokens)
    chunks = _enforce_max_tokens(chunks, max_tokens)
    for chunk in chunks:
        chunk.file_mtime = file_mtime
    logger.debug("Chunked file %s into %d chunks", path, len(chunks))
    return chunks
