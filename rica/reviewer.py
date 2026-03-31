"""L5 Review Mode — codebase analysis and targeted fix application."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from rica.codegen import _strip_fences
from rica.llm import llm
from rica.models import ReviewIssue, ReviewReport
from rica.registry import LANGUAGE_REGISTRY

# Runtime directories to skip (mirrors L2 filter)
_SKIP_DIRS: frozenset[str] = frozenset(
    {
        ".venv", "venv", "env", "node_modules", "__pycache__",
        ".git", "dist", "build", "target", ".tox",
    }
)

_MAX_BYTES: int = 100_000  # 100 KB


def _detect_language(path: Path) -> str | None:
    """Walk path and return the language with the most matching source files.

    Returns None if the result is ambiguous (tie between two or more languages).
    """
    ext_counts: dict[str, int] = {}
    for f in path.rglob("*"):
        if f.is_file() and not any(p in _SKIP_DIRS for p in f.parts):
            ext = f.suffix.lower()
            ext_counts[ext] = ext_counts.get(ext, 0) + 1

    lang_scores: dict[str, int] = {}
    for lang, info in LANGUAGE_REGISTRY.items():
        ext = info.get("extension", "")
        score = ext_counts.get(ext, 0) if ext else 0
        if score > 0:
            lang_scores[lang] = score

    if not lang_scores:
        return None

    max_score = max(lang_scores.values())
    winners = [lang for lang, score in lang_scores.items() if score == max_score]
    return winners[0] if len(winners) == 1 else None


def _collect_files(path: Path) -> list[Path]:
    """Return all source files under path, skipping runtime directories."""
    files: list[Path] = []
    for f in path.rglob("*"):
        if f.is_file() and not any(part in _SKIP_DIRS for part in f.relative_to(path).parts):
            files.append(f)
    return files


def _load_files(
    path: Path, files: list[Path], console: Console
) -> dict[str, str]:
    """Read file contents. Warn and truncate if total size exceeds _MAX_BYTES.

    Prioritizes files closer to the root, then by size descending within each depth.
    Returns a dict of {relative_path_str: content}.
    """
    # Sort: shallower first, then larger files first within same depth
    files_sorted = sorted(
        files,
        key=lambda f: (len(f.relative_to(path).parts), -f.stat().st_size),
    )

    total = 0
    selected: list[Path] = []
    for f in files_sorted:
        size = f.stat().st_size
        if total + size > _MAX_BYTES and selected:
            console.print(
                Panel(
                    f"[yellow]Codebase exceeds 100 KB. Only the first {len(selected)} files"
                    f" (by proximity to root) will be reviewed.[/yellow]",
                    border_style="dim",
                    title="[yellow]Warning[/yellow]",
                )
            )
            break
        selected.append(f)
        total += size

    result: dict[str, str] = {}
    for f in selected:
        try:
            result[str(f.relative_to(path))] = f.read_text(encoding="utf-8", errors="replace")
        except Exception:
            pass
    return result


def _build_review_prompt(
    path: Path, language: str, files: dict[str, str]
) -> str:
    """Construct the user prompt for the review LLM call."""
    parts: list[str] = [
        f"Directory: {path}",
        f"Language: {language}",
        f"Files to review: {len(files)}",
        "",
    ]
    for rel_path, content in files.items():
        parts.append(f"=== FILE: {rel_path} ===")
        parts.append(content)
        parts.append("")
    return "\n".join(parts)


def review_codebase(
    path: Path,
    language: str | None,
    console: Console,
) -> ReviewReport:
    """Analyze an external codebase and return a structured ReviewReport."""
    # Language detection
    if language is None:
        language = _detect_language(path)
        if language is None:
            console.print(
                Panel(
                    "[red]Could not auto-detect language. Re-run with --lang.[/red]",
                    border_style="dim",
                    title="[red]Error[/red]",
                )
            )
            raise SystemExit(1)
        console.print(f"[dim]Detected language: {language}[/dim]")

    # Collect and load files
    all_files = _collect_files(path)
    file_contents = _load_files(path, all_files, console)

    if not file_contents:
        console.print(
            Panel(
                "[red]No readable source files found.[/red]",
                border_style="dim",
                title="[red]Error[/red]",
            )
        )
        raise SystemExit(1)

    console.print(f"[dim]Reviewing {len(file_contents)} files...[/dim]")

    # Load system prompt
    prompt_path = Path(__file__).parent / "prompts" / "reviewer.txt"
    system_prompt = prompt_path.read_text(encoding="utf-8")

    user_prompt = _build_review_prompt(path, language, file_contents)

    raw = llm.generate(system_prompt, user_prompt)
    raw = _strip_fences(raw)

    # Parse JSON
    try:
        data = json.loads(raw)
        # Inject canonical values that LLM might misreport
        data["path"] = str(path)
        data["language"] = language
        data["files_reviewed"] = len(file_contents)
        report = ReviewReport(**data)
    except Exception as exc:
        console.print(
            Panel(
                f"[red]Failed to parse review response from LLM.[/red]\n\n"
                f"[dim]{exc}[/dim]\n\n"
                f"[dim]Raw output:[/dim]\n{raw[:500]}",
                border_style="dim",
                title="[red]Parse Error[/red]",
            )
        )
        raise SystemExit(1)

    return report


def fix_file(
    file_path: Path,
    issues: list[ReviewIssue],
    all_files: dict[str, str],
    language: str,
    console: Console,
) -> str:
    """Generate a fixed version of file_path addressing the given issues."""
    prompt_path = Path(__file__).parent / "prompts" / "fixer.txt"
    system_prompt = prompt_path.read_text(encoding="utf-8")

    original_content = file_path.read_text(encoding="utf-8", errors="replace")

    issue_lines: list[str] = []
    for i, issue in enumerate(issues, 1):
        line_ref = f" (line {issue.line})" if issue.line else ""
        issue_lines.append(
            f"Issue {i}{line_ref}: {issue.description}\nSuggested fix: {issue.suggestion}"
        )

    context_parts: list[str] = []
    for rel_path, content in all_files.items():
        if rel_path != str(file_path.name):
            context_parts.append(f"=== CONTEXT FILE: {rel_path} ===\n{content}\n")

    user_prompt = "\n".join(
        [
            f"FILE TO FIX: {file_path.name}",
            "",
            "=== CURRENT CONTENT ===",
            original_content,
            "",
            "=== ISSUES TO FIX ===",
            "\n\n".join(issue_lines),
            "",
            "=== OTHER SOURCE FILES (for context) ===",
            "\n".join(context_parts),
        ]
    )

    raw = llm.generate(system_prompt, user_prompt)
    return _strip_fences(raw)
