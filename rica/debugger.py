"""Debug Loop layer for Rica - L4 implementation."""

import json
import re
import uuid
from pathlib import Path
from typing import Optional

from rich.console import Console

from .codegen import _strip_fences
from .config import PLANS_DIR
from .llm import llm
from .localizer import localize
from .models import BuildPlan, EditSpec, ErrorClass
from .patcher import patch_file


def classify_error(stdout: str, stderr: str, language: str, timed_out: bool) -> ErrorClass:
    """Classify an error based on output patterns."""
    if timed_out:
        return ErrorClass(
            category="timeout",
            implicated_files=[],
            error_summary="Process timed out",
            raw_stderr=stderr
        )
    
    # Check for compile errors
    compile_patterns = [
        r"error\[", r"SyntaxError", r"cannot find symbol", r"undefined:",
        r"does not compile", r"build failed", r"error TS"
    ]
    if any(re.search(pattern, stderr, re.IGNORECASE) for pattern in compile_patterns):
        category = "compile_error"
    # Check for import errors
    elif any(pattern in stderr for pattern in [
        "ModuleNotFoundError", "ImportError", "cannot find package",
        "no required module", "cannot find module"
    ]):
        category = "import_error"
    # Check for type errors
    elif any(pattern in stderr for pattern in [
        "TypeError", "type mismatch", "cannot use", "incompatible types"
    ]):
        category = "type_error"
    # Check for assertion errors
    elif any(pattern in stderr for pattern in [
        "AssertionError", "FAILED", "panicked at", "FAIL\t"
    ]):
        category = "assertion_error"
    # Runtime error (non-zero exit with stderr)
    elif stderr.strip():
        category = "runtime_error"
    else:
        category = "unknown"
    
    # Extract implicated files based on language
    implicated_files = []
    
    if language.lower() == "python":
        matches = re.findall(r'File "([^"]+)", line \d+', stderr)
        implicated_files = matches
    elif language.lower() == "go":
        matches = re.findall(r'^([^.]+\.go):\d+:\d+:', stderr, re.MULTILINE)
        implicated_files = matches
    elif language.lower() == "rust":
        matches = re.findall(r'--> ([^.]+\.rs):\d+:\d+', stderr)
        implicated_files = matches
    else:
        # Generic fallback - look for file extensions
        extensions = [".py", ".go", ".rs", ".js", ".ts", ".rb", ".sh"]
        for ext in extensions:
            pattern = rf'\b(\S+{ext})\b'
            matches = re.findall(pattern, stderr)
            implicated_files.extend(matches)
    
    # Normalize paths (strip leading "./") and deduplicate
    normalized_files = []
    seen = set()
    for file_path in implicated_files:
        normalized = file_path.lstrip("./")
        if normalized not in seen:
            seen.add(normalized)
            normalized_files.append(normalized)
    
    # Get error summary (first non-empty line, truncated)
    error_lines = [line.strip() for line in stderr.splitlines() if line.strip()]
    error_summary = error_lines[0][:120] if error_lines else "No error details"
    
    return ErrorClass(
        category=category,
        implicated_files=normalized_files,
        error_summary=error_summary,
        raw_stderr=stderr
    )


def _attempt_patch_fix(
    error: ErrorClass,
    file_path: Path,
    localized_line: int,
    session_id: str | None,
    console: Console,
):
    """
    Try to fix a localised fault via targeted patch rather than whole-file rewrite.
    Returns a PatchResult on success/failure, or None if the attempt cannot proceed.
    """
    try:
        content = file_path.read_text(encoding="utf-8")
        lines = content.splitlines()
        total_lines = len(lines)
        if total_lines == 0:
            return None

        start_line = max(1, localized_line - 2)
        end_line = min(total_lines, localized_line + 2)

        original_snippet = "\n".join(
            f"{i + 1}: {lines[i]}" for i in range(start_line - 1, end_line)
        )

        prompt_path = Path(__file__).parent / "prompts" / "patcher.txt"
        template = prompt_path.read_text().strip()

        prompt = template
        prompt = prompt.replace("{{filepath}}", str(file_path))
        prompt = prompt.replace("{{start_line}}", str(start_line))
        prompt = prompt.replace("{{end_line}}", str(end_line))
        prompt = prompt.replace("{{original_lines}}", original_snippet)
        prompt = prompt.replace("{{error_text}}", error.raw_stderr[:2000])
        prompt = prompt.replace("{{fault_site}}", f"{file_path}:{localized_line}")

        raw = llm.generate(
            system_prompt="",
            user_prompt=prompt,
            layer="L22",
            call_type="patch",
            session_id=session_id,
        )

        replacement_lines = raw.splitlines()
        edit_spec = EditSpec(
            filepath=file_path,
            start_line=start_line,
            end_line=end_line,
            replacement_lines=replacement_lines,
            description=f"Patch fix for {error.error_summary[:80]}",
        )
        return patch_file(file_path, edit_spec, validate_cmd=None)

    except Exception:
        return None


def generate_fix(
    error: ErrorClass,
    file_path: Path,
    workspace: Path,
    plan: BuildPlan,
    console: Console,
    *,
    session_id: str | None = None
) -> str:
    """Generate a fix for a given error."""
    # Read current content of the file
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            current_content = f.read()
    except Exception as e:
        console.print(f"[red]Error reading file {file_path}: {e}[/red]")
        return current_content
    
    # Collect workspace context
    context_parts = []
    total_chars = 0
    max_chars = 12000
    
    # Walk workspace for context files
    for path in sorted(workspace.rglob("*")):
        if path.is_dir() or path == file_path:
            continue
        
        # Skip certain extensions
        skip_extensions = {".lock", ".sum", ".log", ".db", ".json"}
        source_extensions = {".py", ".go", ".rs", ".js", ".ts", ".sh", ".rb", ".java", ".cs", ".cpp", ".c", ".h"}
        
        if path.suffix in skip_extensions and path.suffix not in source_extensions:
            continue
        
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            
            relative_path = path.relative_to(workspace)
            file_block = f"### File: {relative_path}\n{content}\n"
            
            if total_chars + len(file_block) > max_chars:
                # Truncate the last file to stay within limit
                remaining_chars = max_chars - total_chars
                if remaining_chars > 100:  # Only add if we have meaningful space
                    truncated_content = content[:remaining_chars-50] + "\n... (truncated)"
                    file_block = f"### File: {relative_path}\n{truncated_content}\n"
                    context_parts.append(file_block)
                break
            
            context_parts.append(file_block)
            total_chars += len(file_block)
            
        except Exception:
            # Skip files that can't be read
            continue
    
    context_block = "\n".join(context_parts)
    
    # Load system prompt
    try:
        prompt_path = Path(__file__).parent / "prompts" / "debugger.txt"
        system_prompt = prompt_path.read_text().strip()
    except Exception as e:
        console.print(f"[red]Error loading debugger prompt: {e}[/red]")
        return current_content
    
    # Localize fault sites
    localized = localize(error_output=error.raw_stderr, repo_path=workspace)
    localized_block = ""
    if localized:
        loc_lines = "\n".join(
            f"{p}:{ln} — {reason}" for p, ln, reason in localized
        )
        localized_block = f"\nLocalized fault sites (ranked):\n{loc_lines}\n"

    # Attempt patch-based fix when the top hit is a stack-trace line in this file
    if localized:
        top_file, top_line, top_reason = localized[0]
        if top_reason == "stack_trace" and top_line > 0 and top_file == file_path:
            patch_result = _attempt_patch_fix(
                error=error,
                file_path=file_path,
                localized_line=top_line,
                session_id=session_id,
                console=console,
            )
            if patch_result is not None and patch_result.success and not patch_result.rolled_back:
                try:
                    return file_path.read_text(encoding="utf-8")
                except Exception:
                    pass
            # Failed or rolled back — fall through to whole-file rewrite

    # Build user prompt
    user_prompt = f"""BuildPlan
{plan.model_dump_json(indent=2)}
Error Classification
Category: {error.category}
Summary: {error.error_summary}
Raw stderr:
{error.raw_stderr}
File to Fix: {file_path.name}
{current_content}
Other Workspace Files (for context)
{context_block}{localized_block}
Return ONLY the complete fixed content of {file_path.name}."""
    
    # Generate fix
    try:
        result = llm.generate(system_prompt=system_prompt, user_prompt=user_prompt, layer="L4", call_type="debug", session_id=session_id)
        
        # Strip fences and clean
        cleaned = _strip_fences(result)
        cleaned = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', cleaned)
        
        return cleaned
        
    except Exception as e:
        console.print(f"[red]Error generating fix: {e}[/red]")
        return current_content
