"""Code generation layer for Rica - L2 implementation."""

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import List

from rich.console import Console

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


def _strip_fences(content: str) -> str:
    """Remove markdown code fences from LLM output."""
    lines = content.splitlines()

    # Strip opening fence (```lang or ``` on first non-empty line)
    if lines and lines[0].strip().startswith("```"):
        lines = lines[1:]

    # Strip closing fence (``` on last non-empty line)
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]

    return "\n".join(lines)


def build_project(plan: BuildPlan, workspace: Path, console: Console) -> List[GeneratedFile]:
    """Build a project from a plan, generating all files."""
    generated_files: List[GeneratedFile] = []
    
    # Flatten and deduplicate — last occurrence of each path wins
    file_map: dict[str, FilePlan] = {}
    for milestone in plan.milestones:
        for f in milestone.files:
            file_map[f.path] = f  # later milestone overwrites earlier
    
    all_files = list(file_map.values())
    
    # Filter out auto-generated lock files
    filtered_files = [
        f for f in file_map.values()
        if Path(f.path).name not in NEVER_GENERATE
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
            f"  [dim]Skipping {skipped} auto-generated file(s) "
            f"(lock files — run package manager after build)[/dim]"
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
        
        # Create GeneratedFile record
        generated_file = GeneratedFile(
            path=file_plan.path,
            content=content,
            language=file_plan.language,
            generated_at=datetime.utcnow().isoformat() + "Z"
        )
        generated_files.append(generated_file)
    
    console.print()
    
    # Write rica.lock file
    _write_lock_file(plan, workspace, generated_files)
    
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


def _write_lock_file(plan: BuildPlan, workspace: Path, generated_files: List[GeneratedFile]) -> None:
    """Write a rica.lock file to track the build."""
    lock_data = {
        "session_id": plan.session_id,
        "goal": plan.goal,
        "language": plan.language,
        "built_at": datetime.utcnow().isoformat() + "Z",
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
