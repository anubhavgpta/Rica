"""Code generation layer for Rica - L2 implementation."""

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .db import db
from .llm import llm
from .models import BuildPlan, FilePlan, GeneratedFile

# Files that must never be LLM-generated — always produced by package managers
NEVER_GENERATE: frozenset[str] = frozenset({
    "Cargo.lock",        # Rust / cargo
    "package-lock.json", # Node / npm
    "yarn.lock",         # Node / yarn
    "pnpm-lock.yaml",    # Node / pnpm
    "poetry.lock",       # Python / poetry
    "go.sum",            # Go / go mod
    "Gemfile.lock",      # Ruby / bundler
    "composer.lock",     # PHP / composer
    "mix.lock",          # Elixir / mix
    "pubspec.lock",      # Dart / flutter
})

# Directory names that should never be generated
BLOCKED_DIRS: frozenset[str] = frozenset({
    ".venv", "venv", "env", "node_modules", "__pycache__", 
    ".git", "dist", "build", "target", ".tox"
})


def _should_skip_path(file_path: str) -> bool:
    """Check if a file path should be skipped based on filtering rules."""
    path = Path(file_path)
    
    # Skip if filename is in NEVER_GENERATE
    if path.name in NEVER_GENERATE:
        return True
    
    # Skip if first component is a blocked directory
    if path.parts and path.parts[0] in BLOCKED_DIRS:
        return True
    
    # Skip bare directory entries (no extension) that aren't known dotfiles
    if not path.suffix and not path.name.startswith('.'):
        return True
    
    return False


def _strip_fences(content: str) -> str:
    """Remove markdown code fences and control characters from LLM output."""
    if content is None:
        return ""
    
    lines = content.splitlines()

    # Strip opening fence (```lang or ``` on first non-empty line)
    if lines and lines[0].strip().startswith("```"):
        lines = lines[1:]

    # Strip closing fence (``` on last non-empty line)
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]

    # Rejoin and remove non-printable control characters (except \n and \t)
    cleaned_content = "\n".join(lines)
    cleaned_content = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', cleaned_content)
    
    # Also remove literal control sequences like <ctrlXX>
    cleaned_content = re.sub(r'<ctrl\d+>', '', cleaned_content)
    
    return cleaned_content


def build_project(plan: BuildPlan, workspace: Path, console: Console) -> List[GeneratedFile]:
    """Build a project from a plan, generating all files."""
    generated_files: List[GeneratedFile] = []
    
    # Flatten and deduplicate — last occurrence of each path wins
    file_map: dict[str, FilePlan] = {}
    for milestone in plan.milestones:
        for f in milestone.files:
            file_map[f.path] = f  # later milestone overwrites earlier
    
    all_files = list(file_map.values())
    
    # Filter out auto-generated and blocked files
    filtered_files = [
        f for f in file_map.values()
        if not _should_skip_path(f.path)
    ]
    
    skipped = len(all_files) - len(filtered_files)
    all_files = filtered_files
    total = len(all_files)
    
    console.print(f"Building project: {plan.goal}")
    console.print(f"Language: {plan.language}")
    console.print(f"Files to generate: {total}")
    console.print()
    
    if skipped > 0:
        console.print(
            f"  [dim]Skipping {skipped} auto-generated/blocked file(s) "
            f"(lock files, system dirs, etc.)[/dim]"
        )
    
    console.print(f"Generating {total} unique files...")
    
    # Iterate through deduplicated files
    for i, file_plan in enumerate(all_files, 1):
        # Construct full target path
        target_path = workspace / file_plan.path
        
        # Skip if file already exists (resumability)
        if target_path.exists():
            console.print(f"  [dim]Skipping (already written): {file_plan.path}[/dim]")
            continue
        
        # Show progress
        console.print(f"  Generating [{i}/{total}] {file_plan.path}")
        
        # Build user prompt
        user_prompt = _build_user_prompt(plan, file_plan, generated_files)
        
        # Generate file content
        raw = llm.generate(CODEGEN_SYSTEM_PROMPT, user_prompt)
        content = _strip_fences(raw)
        
        # Create parent directories
        target_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Write content to disk
        with open(target_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        # Create GeneratedFile record with language tagging
        file_language = file_plan.language_tag.language if file_plan.language_tag else file_plan.language
        generated_file = GeneratedFile(
            path=file_plan.path,
            content=content,
            language=file_language,
            generated_at=datetime.now(timezone.utc).isoformat() + "Z"
        )
        generated_files.append(generated_file)
    
    console.print()
    
    # Post-build step: write conftest.py for Python projects with src/ layout
    _write_conftest_if_needed(plan, workspace, console)
    
    # Write rica.lock file
    _write_lock_file(plan, workspace, generated_files)
    
    # Show per-language file summary
    _show_language_summary(generated_files, console)
    
    return generated_files


def _build_user_prompt(plan: BuildPlan, file_plan: FilePlan, generated_files: List[GeneratedFile]) -> str:
    """Build the user prompt for file generation."""
    prompt_parts = []
    
    # Build plan section
    prompt_parts.append("--- BUILD PLAN ---")
    prompt_parts.append(plan.model_dump_json(indent=2))
    prompt_parts.append("")
    
    # File to generate section
    prompt_parts.append("--- FILE TO GENERATE ---")
    prompt_parts.append(f"Path: {file_plan.path}")
    prompt_parts.append(f"Language: {file_plan.language}")
    prompt_parts.append(f"Description: {file_plan.description}")
    prompt_parts.append(f"Dependencies: {file_plan.dependencies}")
    prompt_parts.append("")
    
    # Previously generated files section
    prompt_parts.append("--- PREVIOUSLY GENERATED FILES ---")
    if generated_files:
        for gen_file in generated_files:
            prompt_parts.append(f"### {gen_file.path}")
            prompt_parts.append(gen_file.content)
            prompt_parts.append("")
    else:
        prompt_parts.append("(No previously generated files - this is the first file)")
    
    return "\n".join(prompt_parts)


def _write_conftest_if_needed(plan: BuildPlan, workspace: Path, console: Console) -> None:
    """Write conftest.py for Python projects with src/ layout if needed."""
    # Only for Python projects
    if plan.language.lower() != "python":
        return
    
    # Check if src/ directory exists
    src_dir = workspace / "src"
    if not src_dir.exists() or not src_dir.is_dir():
        return
    
    # Check if conftest.py already exists in workspace root
    conftest_path = workspace / "conftest.py"
    if conftest_path.exists():
        return
    
    # Write conftest.py content
    conftest_content = """import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / "src"))
"""
    
    try:
        with open(conftest_path, 'w', encoding='utf-8') as f:
            f.write(conftest_content)
        console.print(f"  [dim]Generated conftest.py for src/ layout[/dim]")
    except Exception as e:
        console.print(f"  [yellow]Warning: Could not write conftest.py: {e}[/yellow]")


def _show_language_summary(generated_files: List[GeneratedFile], console: Console) -> None:
    """Display a summary panel grouping generated files by language."""
    if not generated_files:
        return
    
    # Count files by language
    language_counts: dict[str, int] = {}
    for gen_file in generated_files:
        lang = gen_file.language
        language_counts[lang] = language_counts.get(lang, 0) + 1
    
    # Create summary table
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Language", style="bold", min_width=15)
    table.add_column("Files", justify="right", min_width=5)
    
    for language, count in sorted(language_counts.items()):
        table.add_row(language, str(count))
    
    console.print()
    console.print(Panel(
        table,
        title="Build Summary",
        border_style="dim"
    ))


def _write_lock_file(plan: BuildPlan, workspace: Path, generated_files: List[GeneratedFile]) -> None:
    """Write a rica.lock file to track the build."""
    lock_data = {
        "session_id": plan.session_id,
        "goal": plan.goal,
        "language": plan.language,
        "built_at": datetime.now(timezone.utc).isoformat() + "Z",
        "files": [
            {
                "path": gen_file.path,
                "language": gen_file.language,
                "bytes": len(gen_file.content.encode('utf-8'))
            }
            for gen_file in generated_files
        ]
    }
    
    lock_path = workspace / "rica.lock"
    with open(lock_path, 'w', encoding='utf-8') as f:
        json.dump(lock_data, f, indent=2)


# Load the system prompt from file
def _load_system_prompt() -> str:
    """Load the codegen system prompt from file."""
    prompt_path = Path(__file__).parent / "prompts" / "codegen.txt"
    with open(prompt_path, 'r', encoding='utf-8') as f:
        return f.read().strip()

CODEGEN_SYSTEM_PROMPT = _load_system_prompt()
