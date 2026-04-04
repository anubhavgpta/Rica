"""L7 Explain Mode — codebase explanation generation."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from rich.console import Console

from rica.codegen import _strip_fences
from rica.llm import llm
from rica.models import ExplainReport
from rica.registry import LANGUAGE_REGISTRY, detect_languages

# Runtime directories to skip (mirrors L5 filter)
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
                f"[dim]Codebase exceeds 100 KB. Only the first {len(selected)} files"
                f" (by proximity to root) will be analyzed.[/dim]"
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


def explain_codebase(path: Path, language: str, console: Console, *, session_id: str | None = None) -> ExplainReport:
    """Generate a plain-English explanation of a codebase."""
    # Language detection for multi-language support
    if language == "auto" or "," in language:
        detected_languages = detect_languages(path)
        if detected_languages == ["unknown"]:
            console.print(
                "[red]Could not auto-detect language. Re-run with --lang.[/red]"
            )
            raise RuntimeError("Could not detect programming language")
        language = ",".join(detected_languages)
        console.print(f"[dim]Detected languages: {language}[/dim]")
    
    # Collect and load files
    all_files = _collect_files(path)
    file_contents = _load_files(path, all_files, console)

    if not file_contents:
        console.print(
            "[red]No readable source files found.[/red]"
        )
        raise RuntimeError("No readable source files found")

    console.print(f"[dim]Collected {len(file_contents)} files for analysis...[/dim]")

    # Build file contents for prompt
    file_blocks: list[str] = []
    for rel_path, content in file_contents.items():
        file_blocks.append(f"### {rel_path}")
        file_blocks.append(content)
        file_blocks.append("")

    file_contents_str = "\n".join(file_blocks)

    # Load and format prompt
    prompt_path = Path(__file__).parent / "prompts" / "explainer.txt"
    prompt_template = prompt_path.read_text(encoding="utf-8")
    
    # Add language-aware prefix for multi-language codebases
    if "," in language:
        language_prefix = f"This codebase contains: {language}. Please cover all languages in your explanation.\n\n"
    else:
        language_prefix = ""
    
    formatted_prompt = language_prefix + prompt_template.format(
        language=language,
        path=path,
        file_contents=file_contents_str
    )

    console.print("[dim]Generating explanation...[/dim]")

    # Call LLM
    raw = llm.generate(system_prompt="", user_prompt=formatted_prompt, layer="L7", call_type="explain", session_id=session_id)
    explanation = _strip_fences(raw).strip()

    if not explanation:
        raise RuntimeError("LLM returned an empty explanation")

    return ExplainReport(
        path=str(path),
        language=language,
        files_analyzed=len(file_contents),
        explanation=explanation,
        explained_at=datetime.now(timezone.utc).isoformat() + "Z"
    )
