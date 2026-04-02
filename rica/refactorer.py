"""L8 Refactor Mode — codebase refactoring."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from rich.console import Console
from rich.panel import Panel

from rica.codegen import _strip_fences
from rica.llm import llm
from rica.models import RefactorChange, RefactorReport
from rica.registry import LANGUAGE_REGISTRY, detect_languages

# Runtime directories to skip (mirrors L5/L6/L7 filter)
_SKIP_DIRS: frozenset[str] = frozenset(
    {
        ".venv", "venv", "env", "node_modules", "__pycache__",
        ".git", "dist", "build", "target", ".tox",
    }
)

_MAX_BYTES: int = 100_000  # 100 KB


def _sanitize_json_string_literals(raw: str) -> str:
    """
    Replace unescaped literal newlines inside JSON string values with \n.
    Handles the case where an LLM returns multi-line content inside a JSON
    string without properly escaping newlines.
    """
    result = []
    in_string = False
    escape_next = False
    for char in raw:
        if escape_next:
            result.append(char)
            escape_next = False
        elif char == '\\':
            result.append(char)
            escape_next = True
        elif char == '"' and not escape_next:
            in_string = not in_string
            result.append(char)
        elif in_string and char == '\n':
            result.append('\\n')
        elif in_string and char == '\r':
            result.append('\\r')
        elif in_string and char == '\t':
            result.append('\\t')
        else:
            result.append(char)
    return ''.join(result)


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


def _collect_files(path: Path, language: str) -> list[Path]:
    """Return all source files under path for the given language, skipping runtime directories."""
    files: list[Path] = []
    ext = LANGUAGE_REGISTRY[language].get("extension", "")
    
    for f in path.rglob("*"):
        if (f.is_file() and 
            not any(part in _SKIP_DIRS for part in f.relative_to(path).parts) and
            f.suffix.lower() == ext):
            files.append(f)
    return files


def _load_files(
    path: Path, files: list[Path], console: Console
) -> dict[str, str]:
    """Read file contents. Warn and truncate if total size exceeds _MAX_BYTES.

    Prioritizes files closer to the root, then by size ascending within each depth.
    Returns a dict of {relative_path_str: content}.
    """
    # Sort: shallower first, then smaller files first within same depth
    files_sorted = sorted(
        files,
        key=lambda f: (len(f.relative_to(path).parts), f.stat().st_size),
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


def refactor_codebase(path: Path, goal: str, language: str | None, console: Console) -> RefactorReport:
    """Generate a refactor plan for a codebase."""
    # Language detection
    if language is None or language == "auto" or "," in language:
        detected_languages = detect_languages(path)
        if detected_languages == ["unknown"]:
            console.print(
                "[red]Could not detect programming language. Please specify --lang.[/red]"
            )
            raise RuntimeError("Could not detect programming language")
        language = ",".join(detected_languages)
        console.print(f"[dim]Detected languages: {language}[/dim]")
    
    # Split languages for multi-language processing
    languages = [lang.strip() for lang in language.split(",")]
    
    all_changes = []
    total_files_analyzed = 0
    
    for lang in languages:
        if not LANGUAGE_REGISTRY.get(lang):
            console.print(
                f"[red]Unsupported language: {lang}[/red]"
            )
            continue
            
        console.print(f"[dim]Analyzing {lang} files...[/dim]")
        
        # Collect and load files for this language
        all_files = _collect_files(path, lang)
        file_contents = _load_files(path, all_files, console)
        
        if not file_contents:
            console.print(f"[dim]No {lang} files found.[/dim]")
            continue
        
        total_files_analyzed += len(file_contents)
        console.print(f"[dim]Collected {len(file_contents)} {lang} files for analysis...[/dim]")
        
        # Build file contents for prompt
        file_blocks: list[str] = []
        for rel_path, content in file_contents.items():
            file_blocks.append(f"### {rel_path}")
            file_blocks.append(content)
            file_blocks.append("")
        
        file_contents_str = "\n".join(file_blocks)
        
        # Load and format prompt
        if len(languages) > 1:
            prompt_path = Path(__file__).parent / "prompts" / "refactorer_multilang.txt"
            prompt_template = prompt_path.read_text(encoding="utf-8")
            formatted_prompt = prompt_template.format(
                LANGUAGE=lang,
                goal=goal,
                file_contents=file_contents_str
            )
        else:
            prompt_path = Path(__file__).parent / "prompts" / "refactorer.txt"
            prompt_template = prompt_path.read_text(encoding="utf-8")
            formatted_prompt = prompt_template.format(
                goal=goal,
                file_contents=file_contents_str
            )
        
        console.print(f"[dim]Generating {lang} refactor plan...[/dim]")
        
        # Call LLM
        raw = llm.generate(system_prompt="", user_prompt=formatted_prompt)
        json_str = _strip_fences(raw).strip()
        
        if not json_str:
            console.print(f"[dim]No {lang} refactor changes generated.[/dim]")
            continue
        
        # Parse JSON response
        try:
            sanitized_json_str = _sanitize_json_string_literals(json_str)
            changes_data = json.loads(sanitized_json_str)
            if not isinstance(changes_data, list):
                raise ValueError("Response is not a JSON array")
            
            lang_changes = [RefactorChange(path=change["path"], content=change["content"]) 
                          for change in changes_data]
            all_changes.extend(lang_changes)
            
        except (json.JSONDecodeError, ValueError, KeyError) as e:
            console.print(
                Panel(
                    f"Failed to parse {lang} refactor response as JSON array:\n{str(e)}\n\nRaw response:\n{json_str[:500]}",
                    title=f"{lang.title()} Parse Error",
                    border_style="red"
                )
            )
            continue
    
    return RefactorReport(
        path=str(path),
        language=language,
        goal=goal,
        files_analyzed=total_files_analyzed,
        changes=all_changes,
        refactored_at=datetime.now(timezone.utc).isoformat() + "Z"
    )


def apply_refactor(report: RefactorReport, path: Path, console: Console) -> None:
    """Apply a refactor report by writing changed files to disk."""
    if not report.changes:
        console.print("[dim]No files to change.[/dim]")
        return

    console.print(f"[dim]Applying {len(report.changes)} file changes...[/dim]")
    
    for change in report.changes:
        target_path = path / change.path
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(change.content, encoding="utf-8")
        console.print(f"[dim]Updated: {change.path}[/dim]")
    
    console.print(
        Panel(
            f"Successfully updated {len(report.changes)} file(s)",
            title="Refactor Applied",
            border_style="green"
        )
    )
