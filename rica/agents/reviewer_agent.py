import ast
import importlib.util
import json
import threading
from pathlib import Path
from contextlib import contextmanager

import google.genai as genai
from loguru import logger


class ReviewerAgent:
    def __init__(self, config: dict):
        self.config = config
        self.client = genai.Client(
            api_key=config["api_key"]
        )
        self.review_timeout = int(config.get("review_timeout", 30))

    def _call_with_timeout(self, func, timeout_seconds, *args, **kwargs):
        """Execute function with timeout using threading."""
        result = [None]
        exception = [None]
        
        def target():
            try:
                result[0] = func(*args, **kwargs)
            except Exception as e:
                exception[0] = e
        
        thread = threading.Thread(target=target)
        thread.daemon = True
        thread.start()
        thread.join(timeout_seconds)
        
        if thread.is_alive():
            logger.warning(f"[reviewer] Operation timed out after {timeout_seconds}s")
            raise TimeoutError(f"Operation timed out after {timeout_seconds} seconds")
        
        if exception[0]:
            raise exception[0]
        
        return result[0]

    def review(
        self,
        task: dict,
        generated_files: list[str],
        workspace_dir: str,
        project_dir: str | None = None,
        snapshot=None,
    ) -> dict:
        issues = []
        for file_path in generated_files:
            path = Path(file_path)
            if not path.exists():
                issues.append(
                    f"Generated file missing: {path.name}"
                )
                continue

            if path.suffix == ".py":
                issues.extend(
                    self._check_python_file(
                        path,
                        project_dir or workspace_dir,
                    )
                )

        issues.extend(
            self._review_with_model(
                task,
                generated_files,
                workspace_dir,
                project_dir,
                snapshot,
            )
        )
        unique_issues = list(dict.fromkeys(issues))
        
        # Filter for critical issues only
        critical_issues = [
            issue for issue in unique_issues
            if self._is_critical_issue(issue)
        ]
        
        revision_tasks = [
            {
                "id": f"{task['id']}-review-{index}",
                "description": (
                    f"Revise generated code for task "
                    f"{task['id']}: {issue}"
                ),
                "type": "fix",
                "status": "pending",
                "source": "reviewer",
            }
            for index, issue in enumerate(
                critical_issues, start=1
            )
        ]
        return {
            "approved": not critical_issues,
            "issues": critical_issues,
            "revision_tasks": revision_tasks,
        }

    def _check_python_file(
        self,
        path: Path,
        project_root: str,
    ) -> list[str]:
        content = path.read_text(
            encoding="utf-8"
        )
        issues = []
        try:
            tree = ast.parse(content)
        except SyntaxError as error:
            return [
                (
                    f"Syntax error in {path.name}: "
                    f"{error.msg} at line {error.lineno}"
                )
            ]

        dependencies = self._dependency_manifest(
            Path(project_root)
        )
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    issue = self._check_import(
                        alias.name,
                        project_root,
                        dependencies,
                    )
                    if issue:
                        issues.append(issue)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    issue = self._check_import(
                        node.module,
                        project_root,
                        dependencies,
                    )
                    if issue:
                        issues.append(issue)
        return issues

    def _check_import(
        self,
        module_name: str,
        project_root: str,
        dependencies: str,
    ) -> str | None:
        root_name = module_name.split(".")[0]
        if importlib.util.find_spec(root_name):
            return None

        project_path = Path(project_root)
        local_module = (
            project_path / f"{root_name}.py"
        )
        local_package = project_path / root_name
        if local_module.exists() or local_package.exists():
            return None

        if root_name.lower() in dependencies.lower():
            return None

        return (
            f"Missing import or dependency: "
            f"{module_name}"
        )

    def _dependency_manifest(
        self,
        project_root: Path,
    ) -> str:
        parts = []
        for name in (
            "requirements.txt",
            "pyproject.toml",
            "package.json",
        ):
            target = project_root / name
            if target.exists():
                parts.append(
                    target.read_text(
                        encoding="utf-8"
                    )
                )
        return "\n".join(parts)

    def _review_with_model(
        self,
        task: dict,
        generated_files: list[str],
        workspace_dir: str,
        project_dir: str | None,
        snapshot,
    ) -> list[str]:
        if not generated_files:
            return []

        snippets = []
        for file_path in generated_files[:3]:
            path = Path(file_path)
            if not path.exists():
                continue
            snippets.append(
                f"FILE: {path.name}\n"
                f"{path.read_text(encoding='utf-8')[:4000]}"
            )
        if not snippets:
            return []

        snapshot_summary = (
            snapshot.summary
            if snapshot and not snapshot.is_empty
            else "Fresh project."
        )
        prompt = f"""Review this code before execution.
Check for:
- syntax errors
- missing imports  
- incorrect paths
- dependency issues
- project structure problems

Task: {task.get("description", "")}
Workspace: {workspace_dir}
Project: {project_dir or workspace_dir}
Codebase summary: {snapshot_summary}

Files:
{chr(10).join(snippets)}

Return JSON only with severity levels:
{{"issues": [{{"description": "...", "severity": "high|medium|low"}}]}}

Severity guidelines:
- high: syntax errors, import errors, crashes, security issues
- medium: runtime errors, missing dependencies, logic errors  
- low: style issues, suggestions, optimizations, documentation"""

        try:
            response = self._call_with_timeout(
                self.client.models.generate_content,
                self.review_timeout,
                model=self.config["model"],
                contents=prompt,
            )
            payload = json.loads(
                self._clean_json(response.text)
            )
            issues = payload.get("issues", [])
            if isinstance(issues, list):
                # Handle both old format (strings) and new format (objects with severity)
                processed_issues = []
                for item in issues:
                    if isinstance(item, dict):
                        description = item.get("description", "")
                        severity = item.get("severity", "medium")
                        processed_issues.append(f"{description} (severity: {severity})")
                    elif isinstance(item, str):
                        processed_issues.append(item)
                
                return [
                    str(item).strip()
                    for item in processed_issues
                    if str(item).strip()
                ]
        except TimeoutError as error:
            logger.warning(
                f"[reviewer] Review timed out after {self.review_timeout}s: {error}"
            )
        except Exception as error:
            logger.debug(
                f"[reviewer] Review fallback: {error}"
            )
        return []

    def _clean_json(self, text: str) -> str:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[-1]
        if cleaned.endswith("```"):
            cleaned = cleaned.rsplit("\n", 1)[0]
        return cleaned.strip()

    def _is_critical_issue(self, issue: str) -> bool:
        """Determine if an issue is critical enough to require revision."""
        issue_lower = issue.lower()
        
        # Check for explicit severity markers
        if "severity: high" in issue_lower:
            return True
        if "severity: medium" in issue_lower:
            return True  # Medium issues still need fixing
        if "severity: low" in issue_lower:
            return False  # Skip low severity issues
        if "severity: critical" in issue_lower:
            return True
        
        # Critical issues that must be fixed (fallback for old format)
        critical_keywords = [
            "syntax error",
            "import error", 
            "name error",
            "type error",
            "attribute error",
            "file not found",
            "permission denied",
            "module not found",
            "undefined",
            "unterminated",
            "invalid syntax",
            "indentation error",
            "key error",
            "index error",
            "value error",
            "connection error",
            "timeout",
            "crash",
            "exception",
            "failed to",
            "no such file",
            "cannot import",
            "not defined"
        ]
        
        # Non-critical issues that shouldn't trigger revisions (expanded list)
        non_critical_keywords = [
            "suggestion",
            "recommendation",
            "consider",
            "could be improved",
            "minor issue",
            "cosmetic",
            "style",
            "design note",
            "best practice",
            "optimization",
            "performance",
            "readability",
            "comment",
            "documentation",
            "typo",
            "spacing",
            "formatting",
            "naming convention",
            "unused import",
            "unused variable",
            "todo",
            "note",
            "suggestion:",
            "recommend:",
            "consider:",
            "could be",
            "might be",
            "should be",
            "would be better",
            "improve",
            "enhance",
            "refactor"
        ]
        
        # Check for critical keywords
        for keyword in critical_keywords:
            if keyword in issue_lower:
                return True
        
        # Check for non-critical keywords
        for keyword in non_critical_keywords:
            if keyword in issue_lower:
                return False
        
        # Default to non-critical for unknown issues (be more conservative)
        return False
