"""Test generation layer for Rica - L8 Part 2 implementation."""

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import List

from rich.console import Console

from .codegen import _strip_fences
from .config import PLANS_DIR
from .db import db, save_test_generation
from .llm import llm
from .models import BuildPlan, GeneratedTest, TestGenReport
from .registry import LANGUAGE_REGISTRY, detect_languages

# Skip directories that should never be analyzed
_SKIP_DIRS = frozenset({
    ".venv", "venv", "env", "node_modules", "__pycache__",
    ".git", "dist", "build", "target", ".tox",
})

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


def _collect_files(path: Path, language: str) -> List[Path]:
    """Return all source files under path for the given language, skipping runtime directories."""
    files: List[Path] = []
    # Make language lookup case-insensitive
    language_key = language.lower()
    if language_key not in LANGUAGE_REGISTRY:
        raise ValueError(f"Unsupported language: {language}")
    ext = LANGUAGE_REGISTRY[language_key].get("extension", "")
    
    for f in path.rglob("*"):
        if (f.is_file() and 
            not any(part in _SKIP_DIRS for part in f.relative_to(path).parts) and
            f.suffix.lower() == ext):
            files.append(f)
    return files


def _load_files(
    path: Path, files: List[Path], console: Console
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
    selected: List[Path] = []
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


def generate_tests(session_id: str, console: Console) -> TestGenReport:
    """Generate tests for a given session."""
    # Load BuildPlan
    plan_path = PLANS_DIR / f"{session_id}.json"
    if not plan_path.exists():
        raise FileNotFoundError(f"Build plan not found for session {session_id}. Expected at: {plan_path}")
    
    with open(plan_path, 'r', encoding='utf-8') as f:
        plan_data = json.load(f)
    plan = BuildPlan(**plan_data)
    
    # Locate workspace from builds table
    build_record = db.get_build_by_session(session_id)
    if not build_record:
        raise RuntimeError(f"No build record found for session {session_id}")
    
    workspace = Path(build_record["workspace"])
    if not workspace.exists():
        raise RuntimeError(f"Workspace not found: {workspace}")
    
    console.print(f"Analyzing workspace: {workspace}")
    console.print(f"Goal: {plan.goal}")
    
    # Detect languages for multi-language support
    if hasattr(plan, 'languages') and len(plan.languages) > 1:
        languages = plan.languages
        console.print(f"Languages: {', '.join(str(l) for l in languages)}")
    else:
        languages = [plan.language]
        console.print(f"Language: {plan.language}")
    
    all_tests = []
    total_files_analyzed = 0
    
    for lang in languages:
        console.print(f"[dim]Generating tests for {lang} files...[/dim]")
        
        # Collect source files for this language
        source_files = _collect_files(workspace, lang)
        console.print(f"Found {len(source_files)} {lang} source files")
        
        if not source_files:
            console.print(f"[dim]No {lang} files found.[/dim]")
            continue
        
        # Load file contents with 100KB truncation
        file_contents = _load_files(workspace, source_files, console)
        console.print(f"Loaded {len(file_contents)} {lang} files for analysis")
        total_files_analyzed += len(file_contents)
        
        # Build file contents for prompt
        file_blocks = []
        for rel_path, content in file_contents.items():
            file_blocks.append(f"### {rel_path}")
            file_blocks.append(content)
            file_blocks.append("")
        
        file_contents_str = "\n".join(file_blocks)
        
        # Load appropriate prompt
        if len(languages) > 1:
            prompt_path = Path(__file__).parent / "prompts" / "test_generator_multilang.txt"
            try:
                prompt_template = prompt_path.read_text(encoding="utf-8")
                # Use replace instead of format to avoid brace conflicts
                system_prompt = prompt_template
                system_prompt = system_prompt.replace("{goal}", plan.goal)
                system_prompt = system_prompt.replace("{LANGUAGE}", lang)
                system_prompt = system_prompt.replace("{file_contents}", file_contents_str)
                user_prompt = ""
            except Exception as e:
                console.print(f"[red]DEBUG: Error loading prompt: {e}[/red]")
                raise
        else:
            prompt_path = Path(__file__).parent / "prompts" / "test_generator.txt"
            system_prompt = prompt_path.read_text(encoding="utf-8")
            
            # Build prompt for single language
            prompt_parts = []
            prompt_parts.append("PROJECT GOAL:")
            prompt_parts.append(plan.goal)
            prompt_parts.append("")
            
            prompt_parts.append("LANGUAGE:")
            prompt_parts.append(lang)
            prompt_parts.append("")
            
            prompt_parts.append("FILES:")
            for rel_path, content in file_contents.items():
                prompt_parts.append(f"### {rel_path}")
                prompt_parts.append(content)
                prompt_parts.append("")
            
            user_prompt = "\n".join(prompt_parts)
            
            prompt_parts.append("MILESTONES:")
            for milestone in plan.milestones:
                prompt_parts.append(f"- {milestone.name}: {milestone.description}")
            prompt_parts.append("")
            
            prompt_parts.append("SOURCE FILES:")
            prompt_parts.append(file_contents_str)
            
            system_prompt = system_prompt  # Use the loaded prompt as system prompt
            user_prompt = "\n".join(prompt_parts)
        
        # Call LLM
        console.print(f"[dim]Generating {lang} test suite...[/dim]")
        
        if len(languages) > 1:
            raw_response = llm.generate(system_prompt, "")
        else:
            raw_response = llm.generate(system_prompt="", user_prompt=user_prompt)
            
        cleaned_response = _strip_fences(raw_response)
        
        # Parse JSON response
        try:
            sanitized_response = _sanitize_json_string_literals(cleaned_response)
            tests_data = json.loads(sanitized_response)
            if not isinstance(tests_data, list):
                raise ValueError("Response is not a JSON array")
        except json.JSONDecodeError as e:
            console.print(
                f"[red]Failed to parse {lang} test generation response as JSON: {e}[/red]\n[dim]Raw response:[/dim]\n{cleaned_response[:500]}"
            )
            continue
        
        # Validate test data structure
        lang_tests = []
        for test_item in tests_data:
            if not isinstance(test_item, dict) or "path" not in test_item or "content" not in test_item:
                console.print(f"[red]Invalid test item: {test_item}[/red]")
                raise ValueError("Invalid test format - each item must have 'path' and 'content' fields")
            
            generated_test = GeneratedTest(
                path=test_item["path"],
                content=test_item["content"]
            )
            lang_tests.append(generated_test)
        
        all_tests.extend(lang_tests)
        console.print(f"[dim]Generated {len(lang_tests)} {lang} test files[/dim]")
    
    # Write test files to workspace
    console.print(f"Writing {len(all_tests)} test files...")
    for test in all_tests:
        test_path = workspace / test.path
        test_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(test_path, 'w', encoding='utf-8') as f:
            f.write(test.content)
        
        console.print(f"  [dim]Created: {test.path}[/dim]")
    
    # Create report
    report = TestGenReport(
        session_id=session_id,
        language=",".join(languages),
        goal=plan.goal,
        files_analyzed=total_files_analyzed,
        tests_generated=all_tests,
        generated_at=datetime.now(timezone.utc).isoformat() + "Z"
    )
    
    # Persist result
    save_test_generation(report)
    
    return report


# Load the system prompt from file
def _load_system_prompt() -> str:
    """Load the test generator system prompt from file."""
    prompt_path = Path(__file__).parent / "prompts" / "test_generator.txt"
    with open(prompt_path, 'r', encoding='utf-8') as f:
        return f.read().strip()

TEST_GENERATOR_SYSTEM_PROMPT = _load_system_prompt()
