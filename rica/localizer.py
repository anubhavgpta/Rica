"""
Stack-trace and keyword-based file/line localizer for existing repos.
Pure stdlib. No PyPI dependencies.
"""

import re
from pathlib import Path

_IGNORED_DIRS = frozenset({
    "node_modules", ".venv", "target", "__pycache__", ".git",
    "dist", "build", "site-packages",
})

_SOURCE_EXTENSIONS = frozenset({
    ".py", ".js", ".ts", ".java", ".rs", ".go", ".c", ".cpp", ".h"
})

_PRIORITY = {"stack_trace": 0, "mentioned_in_error": 1, "keyword_match": 2}


def _is_ignored(path: Path) -> bool:
    for part in path.parts:
        if part in _IGNORED_DIRS:
            return True
    return False


def _find_file_under_repo(filename: str, repo_path: Path) -> Path | None:
    candidate = Path(filename)
    if candidate.is_absolute():
        if candidate.exists():
            try:
                candidate.relative_to(repo_path)
                if not _is_ignored(candidate):
                    return candidate
            except ValueError:
                pass
        return None

    candidate = repo_path / filename
    if candidate.exists() and not _is_ignored(candidate):
        return candidate

    basename = Path(filename).name
    try:
        for found in repo_path.rglob(basename):
            if found.is_file() and not _is_ignored(found):
                return found
    except Exception:
        pass

    return None


_STACK_PATTERNS = [
    # Python: File "path/to/file.py", line 42, in func_name
    re.compile(r'File "([^"]+\.py)", line (\d+)'),
    # Node.js with function: at funcName (path/to/file.js:42:10)
    re.compile(r'at\s+\S+\s+\(([^)]+\.(?:js|ts|mjs|cjs)):(\d+):\d+\)'),
    # Node.js bare: at path/to/file.js:42:10
    re.compile(r'at\s+([^(\s][^\s]*\.(?:js|ts|mjs|cjs)):(\d+):\d+(?!\))'),
    # Rust: at src/main.rs:42:5
    re.compile(r'at\s+([^\s:][^\s]*\.rs):(\d+):\d+'),
    # Go: path/to/file.go:42
    re.compile(r'([^\s:][^\s]*\.go):(\d+)(?::\d+)?'),
    # Java: at com.example.Class.method(File.java:42)
    re.compile(r'at\s+[\w$.]+\((\w[^)]*\.java):(\d+)\)'),
]


def _parse_stack_traces(error_output: str, repo_path: Path) -> list[tuple[Path, int, str]]:
    results: list[tuple[Path, int, str]] = []
    seen: set[tuple[Path, int]] = set()

    for pattern in _STACK_PATTERNS:
        for match in pattern.finditer(error_output):
            raw_file = match.group(1)
            line_num = int(match.group(2))

            file_path = _find_file_under_repo(raw_file, repo_path)
            if file_path is None:
                continue

            key = (file_path, line_num)
            if key not in seen:
                seen.add(key)
                results.append((file_path, line_num, "stack_trace"))

    return results


_FILENAME_PATTERN = re.compile(
    r'\b([\w./\\-]+\.(?:py|js|ts|java|rs|go|c|cpp|h))\b'
)


def _parse_mentioned_files(
    error_output: str,
    repo_path: Path,
    stack_files: set[Path],
) -> list[tuple[Path, int, str]]:
    results: list[tuple[Path, int, str]] = []
    seen: set[Path] = set()

    for match in _FILENAME_PATTERN.finditer(error_output):
        filename = match.group(1)
        file_path = _find_file_under_repo(filename, repo_path)
        if file_path is None:
            continue
        if file_path in stack_files:
            continue
        if file_path not in seen:
            seen.add(file_path)
            results.append((file_path, 0, "mentioned_in_error"))

    return results


_IDENT_PATTERN = re.compile(
    r'\b(?:'
    r'[A-Z][a-zA-Z0-9]*[a-z][a-zA-Z0-9]*'         # CamelCase
    r'|[a-z][a-z0-9]*(?:_[a-z0-9]+)+'              # snake_case
    r'|[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+'              # SCREAMING_SNAKE
    r')\b'
)


def _extract_identifiers(error_output: str) -> list[str]:
    identifiers: list[str] = []
    seen: set[str] = set()
    for match in _IDENT_PATTERN.finditer(error_output):
        word = match.group(0)
        if len(word) >= 4 and word not in seen:
            seen.add(word)
            identifiers.append(word)
    return identifiers


def _keyword_search(
    identifiers: list[str],
    repo_path: Path,
    already_seen: set[tuple[Path, int]],
) -> list[tuple[Path, int, str]]:
    if not identifiers:
        return []

    results: list[tuple[Path, int, str]] = []
    seen: set[tuple[Path, int]] = set()

    try:
        source_files = [
            p for p in repo_path.rglob("*")
            if p.is_file()
            and p.suffix in _SOURCE_EXTENSIONS
            and not _is_ignored(p)
        ]
    except Exception:
        return []

    combined = re.compile(
        r'\b(' + '|'.join(re.escape(ident) for ident in identifiers) + r')\b'
    )

    for source_file in source_files:
        try:
            content = source_file.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        for lineno, line in enumerate(content.splitlines(), start=1):
            if combined.search(line):
                key = (source_file, lineno)
                if key not in already_seen and key not in seen:
                    seen.add(key)
                    results.append((source_file, lineno, "keyword_match"))

    return results


def localize(error_output: str, repo_path: Path) -> list[tuple[Path, int, str]]:
    """
    Localize fault sites from error output within a repository.

    Returns a ranked list of (absolute_file_path, line_number, reason) tuples,
    highest confidence first. Returns an empty list if nothing can be localized.
    Never raises.
    """
    try:
        if not error_output:
            return []
        try:
            if not repo_path.exists():
                return []
        except Exception:
            return []

        stack_results = _parse_stack_traces(error_output, repo_path)
        stack_files = {p for p, _, _ in stack_results}
        stack_keys: set[tuple[Path, int]] = {(p, ln) for p, ln, _ in stack_results}

        mentioned_results = _parse_mentioned_files(error_output, repo_path, stack_files)
        mentioned_keys: set[tuple[Path, int]] = {(p, ln) for p, ln, _ in mentioned_results}

        identifiers = _extract_identifiers(error_output)
        keyword_results = _keyword_search(
            identifiers, repo_path, stack_keys | mentioned_keys
        )

        fused: dict[tuple[Path, int], str] = {}
        order: list[tuple[Path, int]] = []

        for file_path, line, reason in stack_results + mentioned_results + keyword_results:
            key = (file_path, line)
            if key not in fused:
                fused[key] = reason
                order.append(key)
            else:
                if _PRIORITY[reason] < _PRIORITY[fused[key]]:
                    fused[key] = reason

        ordered = sorted(order, key=lambda k: _PRIORITY[fused[k]])
        result = [(k[0], k[1], fused[k]) for k in ordered]
        return result[:20]

    except Exception:
        return []
