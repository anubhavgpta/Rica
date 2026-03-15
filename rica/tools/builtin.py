import subprocess
from pathlib import Path

from rica.executor import RicaExecutor


def read_file_tool(
    *,
    task: dict,
    workspace_dir: str,
    project_dir: str | None = None,
    reader=None,
) -> dict:
    path = _resolve_path(
        task.get("path", ""),
        workspace_dir,
        project_dir,
    )
    return {
        "success": path.exists(),
        "output": (
            path.read_text(encoding="utf-8")
            if path.exists()
            else ""
        ),
        "files": [str(path)] if path.exists() else [],
    }


def write_file_tool(
    *,
    task: dict,
    workspace_dir: str,
    project_dir: str | None = None,
    reader=None,
) -> dict:
    path = _resolve_path(
        task.get("path", ""),
        workspace_dir,
        project_dir,
    )
    path.parent.mkdir(
        parents=True, exist_ok=True
    )
    path.write_text(
        task.get("content", ""),
        encoding="utf-8",
    )
    return {
        "success": True,
        "output": str(path),
        "files": [str(path)],
    }


def search_code_tool(
    *,
    task: dict,
    workspace_dir: str,
    project_dir: str | None = None,
    reader=None,
) -> dict:
    base_dir = project_dir or workspace_dir
    if reader is None:
        return {
            "success": False,
            "output": [],
            "files": [],
        }
    matches = reader.search(
        base_dir,
        task.get("query", ""),
    )
    return {
        "success": True,
        "output": matches,
        "files": [item["path"] for item in matches],
    }


def run_command_tool(
    *,
    task: dict,
    workspace_dir: str,
    project_dir: str | None = None,
    reader=None,
) -> dict:
    executor = RicaExecutor(project_dir or workspace_dir)
    return executor.run(task.get("command", ""))


def install_package_tool(
    *,
    task: dict,
    workspace_dir: str,
    project_dir: str | None = None,
    reader=None,
) -> dict:
    package = task.get("package", "").strip()
    if not package:
        return {
            "success": False,
            "output": "No package specified",
            "files": [],
        }
    result = subprocess.run(
        ["python", "-m", "pip", "install", package],
        cwd=project_dir or workspace_dir,
        capture_output=True,
        text=True,
    )
    output = (result.stdout + result.stderr).strip()
    return {
        "success": result.returncode == 0,
        "output": output,
        "files": [],
    }


def _resolve_path(
    raw_path: str,
    workspace_dir: str,
    project_dir: str | None,
) -> Path:
    base_dir = Path(project_dir or workspace_dir)
    path = Path(raw_path)
    if path.is_absolute():
        return path
    return base_dir / path
