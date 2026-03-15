"""Workspace-oriented memory helpers for runtime initialization."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from rica.memory.project_memory import (
    load_memory as _load_memory_file,
    save_memory as _save_memory_file,
    update_memory as _update_memory_file,
)


def load_memory(
    workspace_dir: str,
    goal: str = "",
) -> dict[str, Any]:
    """Load or create workspace memory immediately after workspace setup."""
    memory_path = Path(workspace_dir) / ".rica_memory.json"
    payload = _load_memory_file(memory_path)
    if goal and not payload.get("goal"):
        payload["goal"] = goal
    _save_memory_file(memory_path, payload)
    return payload


def save_memory(
    workspace_dir: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Persist workspace memory to the standard file path."""
    memory_path = Path(workspace_dir) / ".rica_memory.json"
    return _save_memory_file(memory_path, payload)


def update_memory(
    workspace_dir: str,
    **updates: Any,
) -> dict[str, Any]:
    """Update workspace memory by workspace directory."""
    memory_path = Path(workspace_dir) / ".rica_memory.json"
    return _update_memory_file(memory_path, **updates)
