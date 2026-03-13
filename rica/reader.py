import os
import json
from pathlib import Path
from dataclasses import dataclass
from loguru import logger
from typing import Dict, List

@dataclass
class CodebaseSnapshot:
    project_dir: str
    tree: str
    files: Dict[str, str]
    summary: str
    is_empty: bool
    
    def format_for_prompt(self) -> str:
        if self.is_empty:
            return "Project is empty."
        return (
            f"=== CODEBASE ===\n"
            f"Location: {self.project_dir}\n\n"
            f"Structure:\n{self.tree}\n\n"
            f"Summary: {self.summary}\n\n"
            f"=== FILES ===\n"
            + "\n\n".join(
                f"--- {path} ---\n{content}"
                for path, content in
                self.files.items()
            )
        )

class CodebaseReader:
    """
    Reads and analyzes existing codebases to provide context
    for planning, code generation, and debugging.
    """
    
    INCLUDE_EXTENSIONS = {
        '.py', '.js', '.ts', '.jsx', '.tsx',
        '.html', '.css', '.scss',
        '.json', '.toml', '.yaml', '.yml',
        '.md', '.txt', '.env.example',
        '.sh', '.bat', '.ps1',
        '.sql', '.graphql',
    }
    
    SKIP_DIRS = {
        'node_modules', '.git', '__pycache__',
        '.venv', 'venv', 'env', '.env',
        'dist', 'build', '.next', '.nuxt',
        'coverage', '.pytest_cache',
        'migrations', '.mypy_cache',
    }
    
    SKIP_FILES = {
        'poetry.lock', 'package-lock.json',
        'yarn.lock', 'pnpm-lock.yaml',
        'Pipfile.lock',
    }
    
    MAX_FILE_LINES = 500
    MAX_SNAPSHOT_CHARS = 120_000
    
    def snapshot(
        self,
        project_dir: str,
        goal: str,
        client,
        model: str,
    ) -> CodebaseSnapshot:
        """
        Creates a snapshot of the codebase with structure,
        file contents, and AI-generated summary.
        """
        logger.debug(f"[reader] Creating snapshot of {project_dir}")
        
        # Step 1: Build ASCII tree
        tree = self._build_tree(project_dir)
        
        # Step 2: Read files
        files = self._read_files(project_dir)
        
        # Step 3: Check total size and trim if needed
        if files:
            total_chars = sum(len(content) for content in files.values())
            if total_chars > self.MAX_SNAPSHOT_CHARS:
                files = self._rank_and_trim_files(files, goal, client, model)
        
        # Step 4: Generate summary
        if files:
            summary = self._generate_summary(tree, files, goal, client, model)
            is_empty = False
        else:
            summary = "Empty project — building fresh."
            is_empty = True
        
        snapshot = CodebaseSnapshot(
            project_dir=project_dir,
            tree=tree,
            files=files,
            summary=summary,
            is_empty=is_empty
        )
        
        logger.info(f"[reader] Snapshot: {len(files)} files, is_empty={is_empty}")
        return snapshot
    
    def _build_tree(self, project_dir: str) -> str:
        """Build ASCII tree representation of directory structure."""
        lines = []
        project_name = Path(project_dir).name
        lines.append(f"{project_name}/")
        
        def walk_dir(current_path: Path, prefix: str = ""):
            try:
                entries = sorted(current_path.iterdir(), key=lambda x: (x.is_file(), x.name.lower()))
                for i, entry in enumerate(entries):
                    if entry.name in self.SKIP_DIRS or entry.name.startswith('.'):
                        continue
                    
                    is_last = i == len(entries) - 1
                    current_prefix = "└── " if is_last else "├── "
                    lines.append(f"{prefix}{current_prefix}{entry.name}")
                    
                    if entry.is_dir() and entry.name not in self.SKIP_DIRS:
                        next_prefix = prefix + ("    " if is_last else "│   ")
                        walk_dir(entry, next_prefix)
            except PermissionError:
                pass
        
        walk_dir(Path(project_dir))
        return "\n".join(lines)
    
    def _read_files(self, project_dir: str) -> Dict[str, str]:
        """Read all relevant files in the project directory."""
        files = {}
        project_path = Path(project_dir)
        
        for file_path in project_path.rglob("*"):
            if file_path.is_file():
                # Skip files in skip directories
                if any(skip_dir in file_path.parts for skip_dir in self.SKIP_DIRS):
                    continue
                
                # Skip specific files
                if file_path.name in self.SKIP_FILES:
                    continue
                
                # Check extension
                if file_path.suffix.lower() in self.INCLUDE_EXTENSIONS:
                    try:
                        relative_path = file_path.relative_to(project_dir)
                        content = self._read_file_content(file_path)
                        files[str(relative_path).replace('\\', '/')] = content
                    except (PermissionError, UnicodeDecodeError) as e:
                        logger.debug(f"[reader] Skipping {file_path}: {e}")
        
        return files
    
    def _read_file_content(self, file_path: Path) -> str:
        """Read file content with line limit."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                
                if len(lines) > self.MAX_FILE_LINES:
                    # Keep first MAX_FILE_LINES lines
                    content = ''.join(lines[:self.MAX_FILE_LINES])
                    remaining = len(lines) - self.MAX_FILE_LINES
                    content += f"\n... [truncated: {remaining} more lines]"
                    return content
                else:
                    return ''.join(lines)
        except Exception as e:
            logger.warning(f"[reader] Error reading {file_path}: {e}")
            return f"Error reading file: {e}"
    
    def _rank_and_trim_files(self, files: Dict[str, str], goal: str, client, model: str) -> Dict[str, str]:
        """Use AI to rank files by relevance and keep only the most relevant ones."""
        logger.info(f"[reader] Total chars {sum(len(c) for c in files.values())} exceeds limit, ranking files")
        
        filenames = list(files.keys())
        
        prompt = f"""Given this goal: {goal}
And these files: {json.dumps(filenames, indent=2)}

Which 10-15 files are most relevant to accomplishing the goal?
Consider the file names and extensions to determine relevance.
Return only a JSON list of filenames, no explanations."""

        try:
            response = client.models.generate_content(
                model=model,
                contents=prompt
            )
            
            response_text = response.text.strip()
            cleaned = self._clean_json(response_text)
            
            if not cleaned:
                logger.warning(
                    "[reader] Empty ranking response,"
                    " keeping all files"
                )
                return files  # keep all files as-is
            
            ranked_files = json.loads(cleaned)
            if isinstance(ranked_files, list):
                # Keep only the ranked files
                trimmed_files = {}
                for filename in ranked_files:
                    if filename in files:
                        trimmed_files[filename] = files[filename]
                logger.info(f"[reader] Trimmed to {len(trimmed_files)} most relevant files")
                return trimmed_files
        except Exception as e:
            logger.warning(
                f"[reader] Ranking failed: {e},"
                f" using heuristic fallback"
            )
            # Heuristic fallback: prioritize files mentioned in goal
            goal_lower = goal.lower()
            def score(item):
                name = Path(item[0]).name.lower()
                stem = Path(item[0]).stem.lower()
                return (
                    1 if name in goal_lower else 0,
                    1 if stem in goal_lower else 0,
                    len(item[1])  # prioritize larger files
                )
            
            sorted_files = sorted(
                files.items(),
                key=score,
                reverse=True
            )
            trimmed_files = dict(sorted_files[:15])
            logger.info(f"[reader] Heuristic trimmed to {len(trimmed_files)} files")
            return trimmed_files
    
    def _clean_json(self, text: str) -> str:
        """Clean JSON response by removing markdown fences."""
        import re
        text = text.strip()
        # Strip ```json ... ``` fences
        text = re.sub(
            r'^```(?:json)?\s*', '', text,
            flags=re.MULTILINE
        )
        text = re.sub(
            r'\s*```$', '', text,
            flags=re.MULTILINE
        )
        return text.strip()
    
    def _generate_summary(self, tree: str, files: Dict[str, str], goal: str, client, model: str) -> str:
        """Generate AI summary of the codebase."""
        # Format files for the prompt
        formatted_files = []
        for path, content in files.items():
            # Truncate very long files for the summary
            if len(content) > 2000:
                content = content[:2000] + "\n... [truncated for summary]"
            formatted_files.append(f"--- {path} ---\n{content}")
        
        files_text = "\n\n".join(formatted_files)
        
        prompt = f"""You are a senior engineer doing a codebase review.

Directory tree:
{tree}

Files:
{files_text}

Goal: {goal}

In 3-5 sentences: what does this codebase do, what patterns/stack does it use, and what would need to change to accomplish the goal?"""

        try:
            response = client.models.generate_content(
                model=model,
                contents=prompt
            )
            
            summary = response.text.strip()
            logger.info(f"[reader] Generated summary: {summary[:100]}...")
            return summary
        except Exception as e:
            logger.error(f"[reader] Failed to generate summary: {e}")
            return f"Codebase with {len(files)} files. Error generating summary: {e}"
