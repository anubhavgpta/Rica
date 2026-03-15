"""Workspace metadata helpers used by the controller and memory."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class WorkspaceMetadata:
    """Basic detected metadata about the current project."""

    language: str = "unknown"
    framework: str = "unknown"
    entrypoints: list[str] = field(default_factory=list)
    has_requirements: bool = False
    has_tests: bool = False
    python_files: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "language": self.language,
            "framework": self.framework,
            "entrypoints": self.entrypoints,
            "has_requirements": self.has_requirements,
            "has_tests": self.has_tests,
            "python_files": self.python_files,
        }

    def summary(self) -> str:
        parts = [
            f"language={self.language}",
            f"framework={self.framework}",
            f"entrypoints={len(self.entrypoints)}",
        ]
        if self.has_requirements:
            parts.append("requirements.txt present")
        if self.has_tests:
            parts.append("tests detected")
        return ", ".join(parts)


def detect_workspace_metadata(project_dir: str) -> WorkspaceMetadata:
    """Infer project metadata using portable filesystem inspection."""
    root = Path(project_dir)
    python_files = sorted(
        str(path.relative_to(root)).replace("\\", "/")
        for path in root.rglob("*.py")
        if _should_include(path)
    )
    requirements = root / "requirements.txt"
    tests_dir = root / "tests"
    entrypoints = [
        path
        for path in python_files
        if path.endswith("__main__.py")
        or path == "main.py"
        or path == "app.py"
        or path.startswith("cli")
    ]
    framework = _detect_framework(root, python_files)

    return WorkspaceMetadata(
        language="python" if python_files else "unknown",
        framework=framework,
        entrypoints=entrypoints,
        has_requirements=requirements.exists(),
        has_tests=tests_dir.exists()
        or any("test" in Path(path).parts for path in python_files),
        python_files=python_files,
    )


def _detect_framework(
    root: Path, python_files: list[str]
) -> str:
    requirements = (
        (root / "requirements.txt").read_text(encoding="utf-8")
        if (root / "requirements.txt").exists()
        else ""
    ).lower()
    pyproject = (
        (root / "pyproject.toml").read_text(encoding="utf-8")
        if (root / "pyproject.toml").exists()
        else ""
    ).lower()
    combined = requirements + "\n" + pyproject + "\n" + "\n".join(python_files).lower()
    if "flask" in combined:
        return "flask"
    if "fastapi" in combined:
        return "fastapi"
    if "django" in combined:
        return "django"
    if python_files:
        return "python"
    return "unknown"


def _should_include(path: Path) -> bool:
    skip_dirs = {".git", ".venv", "__pycache__", "build", "dist", ".pytest_cache"}
    return not any(part in skip_dirs for part in path.parts)
