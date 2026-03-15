"""Codebase reading, summarization, and semantic retrieval."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List

from rica.logging_utils import get_component_logger
from rica.search import CodeIndex, build_code_index
from rica.workspace import detect_workspace_metadata

logger = get_component_logger("agent")

# Ignore directories that should never be scanned
IGNORE_DIRS = {
    ".venv",
    "venv",
    "__pycache__",
    ".git",
    "node_modules",
    "dist",
    "build",
    "site-packages",
    ".pytest_cache",
    ".mypy_cache",
    ".tox"
}


def scan_project_structure(project_dir: str | Path) -> dict[str, List[str]]:
    """
    Scan project structure and detect key components.
    
    Returns:
        Dictionary containing:
        - python_files: List of Python file paths
        - tests: List of test file paths  
        - dependencies: List of detected dependencies
        - entrypoints: List of potential entry points
        - config_files: List of configuration files
    """
    project_path = Path(project_dir)
    if not project_path.exists():
        return {
            "python_files": [],
            "tests": [],
            "dependencies": [],
            "entrypoints": [],
            "config_files": []
        }
    
    structure = {
        "python_files": [],
        "tests": [],
        "dependencies": [],
        "entrypoints": [],
        "config_files": []
    }
    
    # Scan for Python files, ignoring specified directories
    for py_file in project_path.rglob("*.py"):
        # Check if file is in an ignored directory
        rel_path = py_file.relative_to(project_path)
        parts = rel_path.parts
        
        # Skip if any part matches an ignored directory
        if any(part in IGNORE_DIRS for part in parts):
            logger.debug(f"[reader] Skipping ignored directory: {rel_path}")
            continue
            
        rel_path_str = str(rel_path)
        structure["python_files"].append(rel_path_str)
        
        # Detect test files
        if (
            "test" in py_file.name.lower() or
            "tests" in str(py_file.parent).lower() or
            py_file.name.startswith("test_") or
            py_file.name.endswith("_test.py")
        ):
            structure["tests"].append(rel_path_str)
        
        # Detect potential entry points
        try:
            content = py_file.read_text(encoding="utf-8")
            if "if __name__ == '__main__':" in content or "app.run()" in content:
                structure["entrypoints"].append(rel_path_str)
            
            # Extract dependencies from imports
            imports = re.findall(r'^(?:from|import)\s+([a-zA-Z_][a-zA-Z0-9_]*)', content, re.MULTILINE)
            for imp in imports:
                if imp not in structure["dependencies"] and not imp.startswith('.'):
                    structure["dependencies"].append(imp)
                    
        except Exception as e:
            logger.warning(f"[reader] Failed to read {py_file.name}: {e}")
    
    # Scan for configuration files, ignoring specified directories
    config_patterns = [
        "requirements.txt",
        "pyproject.toml", 
        "setup.py",
        "Pipfile",
        "poetry.lock",
        "environment.yml",
        ".env",
        "config.py",
        "settings.py"
    ]
    
    for pattern in config_patterns:
        for config_file in project_path.rglob(pattern):
            # Check if file is in an ignored directory
            rel_path = config_file.relative_to(project_path)
            parts = rel_path.parts
            
            # Skip if any part matches an ignored directory
            if any(part in IGNORE_DIRS for part in parts):
                logger.debug(f"[reader] Skipping config in ignored directory: {rel_path}")
                continue
                
            rel_path_str = str(rel_path)
            if rel_path_str not in structure["config_files"]:
                structure["config_files"].append(rel_path_str)
    
    # Extract dependencies from requirements.txt if exists
    requirements_file = project_path / "requirements.txt"
    if requirements_file.exists():
        try:
            req_content = requirements_file.read_text(encoding="utf-8")
            req_deps = [
                line.strip().split('==')[0].split('>=')[0].split('<=')[0]
                for line in req_content.splitlines()
                if line.strip() and not line.startswith('#')
            ]
            structure["dependencies"].extend(req_deps)
        except Exception as e:
            logger.warning(f"[reader] Failed to read requirements.txt: {e}")
    
    logger.info(f"[reader] Scanned {len(structure['python_files'])} project files "
                "(ignored: venv, cache, git)")
    
    return structure


@dataclass
class CodebaseSnapshot:
    """Snapshot of the current project state."""

    project_dir: str
    tree: str
    files: Dict[str, str]
    summary: str
    is_empty: bool
    relevant_snippets: list[dict[str, str | int | float]] = field(
        default_factory=list
    )
    metadata: dict = field(default_factory=dict)

    def format_for_prompt(self) -> str:
        if self.is_empty:
            return "Project is empty."

        sections = [
            "=== CODEBASE ===",
            f"Location: {self.project_dir}",
            "",
            f"Structure:\n{self.tree}",
            "",
            f"Summary: {self.summary}",
        ]
        if self.metadata:
            sections.extend(["", f"Metadata: {self.metadata}"])
        if self.relevant_snippets:
            snippet_text = "\n\n".join(
                (
                    f"--- {item['path']}:{item['start_line']} "
                    f"(score={float(item['score']):.3f}) ---\n"
                    f"{item['snippet']}"
                )
                for item in self.relevant_snippets
            )
            sections.extend(["", "=== RELEVANT SNIPPETS ===", snippet_text])
        sections.extend(
            [
                "",
                "=== FILES ===",
                "\n\n".join(
                    f"--- {path} ---\n{content}"
                    for path, content in self.files.items()
                ),
            ]
        )
        return "\n".join(sections)


class CodebaseReader:
    """Read a project, summarize it, and perform semantic search."""

    INCLUDE_EXTENSIONS = {
        ".py",
        ".js",
        ".ts",
        ".jsx",
        ".tsx",
        ".html",
        ".css",
        ".scss",
        ".json",
        ".toml",
        ".yaml",
        ".yml",
        ".md",
        ".txt",
        ".env.example",
        ".sh",
        ".bat",
        ".ps1",
        ".sql",
        ".graphql",
    }
    SKIP_DIRS = {
        "node_modules",
        ".git",
        "__pycache__",
        ".venv",
        "venv",
        "env",
        ".env",
        "dist",
        "build",
        ".next",
        ".nuxt",
        "coverage",
        ".pytest_cache",
        "migrations",
        ".mypy_cache",
        ".rica_logs",
    }
    SKIP_FILES = {
        "poetry.lock",
        "package-lock.json",
        "yarn.lock",
        "pnpm-lock.yaml",
        "Pipfile.lock",
        ".rica_memory.json",
    }
    MAX_FILE_LINES = 500
    MAX_SNAPSHOT_CHARS = 120_000

    def __init__(self) -> None:
        self._indexes: dict[str, CodeIndex] = {}

    def snapshot(
        self,
        project_dir: str,
        goal: str,
        client,
        model: str,
    ) -> CodebaseSnapshot:
        """Create a snapshot of the codebase plus semantic context."""
        logger.debug(f"[reader] Creating snapshot of {project_dir}")
        tree = self._build_tree(project_dir)
        files = self._read_files(project_dir)
        metadata = detect_workspace_metadata(project_dir).to_dict()

        if files:
            total_chars = sum(len(content) for content in files.values())
            if total_chars > self.MAX_SNAPSHOT_CHARS:
                files = self._rank_and_trim_files(files, goal, client, model)

        relevant_snippets = self._semantic_search(
            project_dir, goal, files, client, model
        )

        if files:
            summary = self._generate_summary(
                tree, files, goal, client, model, metadata
            )
            is_empty = False
        else:
            summary = "Empty project - building fresh."
            is_empty = True

        snapshot = CodebaseSnapshot(
            project_dir=project_dir,
            tree=tree,
            files=files,
            summary=summary,
            is_empty=is_empty,
            relevant_snippets=relevant_snippets,
            metadata=metadata,
        )
        logger.info(
            f"[reader] Snapshot: {len(files)} files, is_empty={is_empty}"
        )
        return snapshot

    def search(
        self,
        project_dir: str,
        query: str,
        limit: int = 5,
        client=None,
        model: str | None = None,
    ) -> List[Dict[str, str | int | float]]:
        """Search code using semantic similarity with a keyword fallback."""
        if not query.strip():
            return []

        files = self._read_files(project_dir)
        index = self._get_or_build_index(
            project_dir, files, client=client, model=model
        )
        matches = index.search(query, top_k=limit)
        if matches:
            return matches

        query_terms = [
            term.lower() for term in query.split() if term.strip()
        ]
        if not query_terms:
            return []

        fallback = []
        for relative_path, content in files.items():
            score = self._keyword_score(
                relative_path, content, query_terms
            )
            if score <= 0:
                continue
            fallback.append(
                {
                    "path": relative_path,
                    "score": float(score),
                    "snippet": self._extract_snippet(content, query_terms),
                    "start_line": 1,
                }
            )
        return sorted(
            fallback,
            key=lambda item: float(item["score"]),
            reverse=True,
        )[:limit]

    def _semantic_search(
        self,
        project_dir: str,
        query: str,
        files: Dict[str, str],
        client,
        model: str,
    ) -> list[dict[str, str | int | float]]:
        if not files or not query.strip():
            return []
        index = self._get_or_build_index(
            project_dir, files, client=client, model=model
        )
        return index.search(query, top_k=5)

    def _get_or_build_index(
        self,
        project_dir: str,
        files: Dict[str, str],
        client=None,
        model: str | None = None,
    ) -> CodeIndex:
        key = str(Path(project_dir).resolve())
        index = self._indexes.get(key)
        if index is None:
            index = build_code_index(
                project_dir,
                files,
                client=client,
                model=model,
            )
            self._indexes[key] = index
        return index

    def invalidate_index(self, project_dir: str) -> None:
        """Drop the cached index for a project after file changes."""
        self._indexes.pop(str(Path(project_dir).resolve()), None)

    def _build_tree(self, project_dir: str) -> str:
        lines = [f"{Path(project_dir).name}/"]

        def walk_dir(current_path: Path, prefix: str = "") -> None:
            try:
                entries = [
                    entry
                    for entry in sorted(
                        current_path.iterdir(),
                        key=lambda item: (item.is_file(), item.name.lower()),
                    )
                    if entry.name not in self.SKIP_DIRS
                    and not entry.name.startswith(".")
                ]
                for index, entry in enumerate(entries):
                    is_last = index == len(entries) - 1
                    branch = "`-- " if is_last else "|-- "
                    lines.append(f"{prefix}{branch}{entry.name}")
                    if entry.is_dir():
                        next_prefix = prefix + ("    " if is_last else "|   ")
                        walk_dir(entry, next_prefix)
            except PermissionError:
                return

        walk_dir(Path(project_dir))
        return "\n".join(lines)

    def _read_files(self, project_dir: str) -> Dict[str, str]:
        files: Dict[str, str] = {}
        project_path = Path(project_dir)
        for file_path in project_path.rglob("*"):
            if not file_path.is_file():
                continue
            if any(skip_dir in file_path.parts for skip_dir in self.SKIP_DIRS):
                continue
            if file_path.name in self.SKIP_FILES:
                continue
            if file_path.suffix.lower() not in self.INCLUDE_EXTENSIONS:
                continue
            try:
                relative_path = file_path.relative_to(project_dir)
                files[str(relative_path).replace("\\", "/")] = self._read_file_content(
                    file_path
                )
            except (PermissionError, UnicodeDecodeError) as error:
                logger.debug(f"[reader] Skipping {file_path}: {error}")
        return files

    def _read_file_content(self, file_path: Path) -> str:
        try:
            lines = file_path.read_text(encoding="utf-8").splitlines(True)
            if len(lines) > self.MAX_FILE_LINES:
                content = "".join(lines[: self.MAX_FILE_LINES])
                remaining = len(lines) - self.MAX_FILE_LINES
                return content + f"\n... [truncated: {remaining} more lines]"
            return "".join(lines)
        except Exception as error:
            logger.warning(f"[reader] Error reading {file_path}: {error}")
            return f"Error reading file: {error}"

    def _rank_and_trim_files(
        self,
        files: Dict[str, str],
        goal: str,
        client,
        model: str,
    ) -> Dict[str, str]:
        logger.info(
            f"[reader] Total chars {sum(len(c) for c in files.values())} exceeds limit"
        )
        filenames = list(files.keys())
        prompt = (
            f"Given this goal: {goal}\n"
            f"And these files: {json.dumps(filenames, indent=2)}\n\n"
            "Which 10-15 files are most relevant? "
            "Return only a JSON list of filenames."
        )
        try:
            response = client.models.generate_content(
                model=model,
                contents=prompt,
            )
            response_text = getattr(response, "text", "") or ""
            cleaned = self._clean_json(response_text)
            if not cleaned:
                return files
            ranked_files = json.loads(cleaned)
            if isinstance(ranked_files, list):
                trimmed = {
                    filename: files[filename]
                    for filename in ranked_files
                    if filename in files
                }
                if trimmed:
                    return trimmed
        except Exception as error:
            logger.warning(f"[reader] Ranking failed: {error}")

        goal_lower = goal.lower()
        sorted_files = sorted(
            files.items(),
            key=lambda item: (
                Path(item[0]).name.lower() in goal_lower,
                Path(item[0]).stem.lower() in goal_lower,
                len(item[1]),
            ),
            reverse=True,
        )
        return dict(sorted_files[:15])

    def _clean_json(self, text: str) -> str:
        cleaned = text.strip()
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.MULTILINE)
        cleaned = re.sub(r"\s*```$", "", cleaned, flags=re.MULTILINE)
        return cleaned.strip()

    def _generate_summary(
        self,
        tree: str,
        files: Dict[str, str],
        goal: str,
        client,
        model: str,
        metadata: dict,
    ) -> str:
        formatted_files = []
        for path, content in files.items():
            display_content = (
                content[:2000] + "\n... [truncated for summary]"
                if len(content) > 2000
                else content
            )
            formatted_files.append(f"--- {path} ---\n{display_content}")
        prompt = f"""You are a senior engineer doing a codebase review.

Directory tree:
{tree}

Project metadata:
{metadata}

Files:
{chr(10).join(formatted_files)}

Goal: {goal}

In 3-5 sentences: what does this codebase do, what stack does it use, and what would need to change to accomplish the goal?"""
        try:
            response = client.models.generate_content(
                model=model,
                contents=prompt,
            )
            summary = (getattr(response, "text", "") or "").strip()
            if summary:
                return summary
        except Exception as error:
            logger.error(f"[reader] Failed to generate summary: {error}")
        return f"Codebase with {len(files)} files. Metadata: {metadata}"

    def _keyword_score(
        self, relative_path: str, content: str, query_terms: List[str]
    ) -> int:
        path_lower = relative_path.lower()
        content_lower = content.lower()
        score = 0
        for term in query_terms:
            score += path_lower.count(term) * 3
            score += content_lower.count(term)
        return score

    def _extract_snippet(
        self,
        content: str,
        query_terms: List[str],
        radius: int = 140,
    ) -> str:
        lowered = content.lower()
        for term in query_terms:
            index = lowered.find(term)
            if index >= 0:
                start = max(0, index - radius)
                end = min(len(content), index + radius)
                return content[start:end].strip()
        return content[: radius * 2].strip()
